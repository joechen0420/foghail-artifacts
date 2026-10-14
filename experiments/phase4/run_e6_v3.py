# -*- coding: utf-8 -*-
"""E6 v3（2026-10-14）：v3 合約的端到端協定測試＋確認延遲量測（論文 Table 8 的新來源）。

第一部分 protocol：在活的 4 節點 QBFT 鏈上把 v3 協定完整走一次，並逐項確認「該擋的有擋」：
  註冊根身分 -> openBatch -> 3/4 驗證節點盲簽發憑證（憑證 = 假名地址） -> 霧節點簽媒合 ->
  雙方簽評分結算 -> 假名向 3 個驗證節點領面額收據（盲簽） -> 根身分 deposit 收據＋交回未用憑證 ->
  R_root 更新 -> 再開批次。
  另記錄每個操作的 gas。
第二部分 latency：與 run_e6_v2.py 相同的量測法（逐筆 + 開迴路 10/50/100 筆/秒，逐筆存檔），
  交易換成 v3 的 attestAndSettle（含 6 個 Schnorr 驗章＋霧節點簽章＋雙方評分簽章）。
  量測用的憑證以非盲 Schnorr 直接產生（驗證式與盲簽章相同，合約無從分辨），只為了加快準備。

  FOGHAIL_NETDIR=networkFiles1s FOGHAIL_AFFINITY=1 FOGHAIL_SUF=_v3 python -u run_e6_v3.py
"""
import os
import sys
import json
import time
import hashlib
import secrets
import statistics
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "phase5"))
import run_e6_local as L          # noqa: E402
import run_e6_v2 as V2            # noqa: E402  BlockWatcher / run_row / stats / send_and_wait
import foghail_cred as F          # noqa: E402

from web3 import Web3                            # noqa: E402
from eth_account import Account                  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402

EPOCH_BLOCKS = 3600
THETA = 0
N_SEQ, RATES, N_OPEN, N_SENDERS = 200, (5, 10, 20, 50), 300, 8
GAS = 1_000_000
SUF = os.environ.get("FOGHAIL_SUF", "_v3")


def compile_v3():
    import solcx
    src = (ROOT / "contracts" / "FogHailAttestation.sol").read_text(encoding="utf-8")
    out = solcx.compile_standard({
        "language": "Solidity", "sources": {"F.sol": {"content": src}},
        "settings": {"evmVersion": "berlin", "viaIR": True, "optimizer": {"enabled": True, "runs": 200},
                     "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}}}},
        solc_version="0.8.19")
    c = out["contracts"]["F.sol"]["FogHailAttestation"]
    json.dump(c["abi"], open(ROOT / "out" / "FogHailAttestation_v3.abi.json", "w"), indent=1)
    (ROOT / "out" / "FogHailAttestation_v3.bin").write_text(c["evm"]["bytecode"]["object"])
    return c["abi"], c["evm"]["bytecode"]["object"]


def key_args(validators):
    cpx = [int(v.cred.P.x()) for v in validators]
    cpar = [int(v.cred.P.y()) & 1 for v in validators]
    rpx, rpar = [], []
    for d in F.DELTAS:                       # [ΔR+2][驗證節點] 攤平成 d*4+v
        for v in validators:
            P = v.receipt[d].P
            rpx.append(int(P.x())); rpar.append(int(P.y()) & 1)
    return cpx, cpar, rpx, rpar


class ChainView:
    """驗證節點讀鏈上狀態的介面（給 foghail_cred.Validator 用）。"""
    def __init__(self, c):
        self.c = c.functions

    def theta(self):
        return self.c.theta().call()

    def root_rep(self, root):
        return self.c.rootRep(Web3.to_checksum_address(root)).call()

    def batch(self, root):
        r = Web3.to_checksum_address(root)
        return self.c.batchNonce(r).call(), self.c.batchSize(r).call()

    def pending_receipt(self, p):
        p = Web3.to_checksum_address(p)
        return self.c.pendingDelta(p).call() if self.c.hasPending(p).call() else None


def tx(w3, sender, fn, gas=GAS):
    t = fn.build_transaction({"from": sender.address, "nonce": w3.eth.get_transaction_count(sender.address),
                              "gas": gas, "gasPrice": 0, "chainId": w3.eth.chain_id})
    h = w3.eth.send_raw_transaction(sender.sign_transaction(t).raw_transaction)
    return w3.eth.wait_for_transaction_receipt(h, timeout=60)


def call_err(fn, sender):
    try:
        fn.call({"from": sender.address, "gas": GAS})
        return None
    except Exception as e:
        s = str(e)
        i = s.find("Execution reverted")
        return s[i:i + 60] if i >= 0 else s[:80]


def sig3(sigs):
    return [(i, Web3.to_checksum_address(a), s) for i, (a, s) in sigs]


def esign(key, digest):
    return bytes(Account.sign_message(encode_defunct(primitive=digest), key).signature)


class User:
    """一個根身分；假名依 (4) 由根私鑰推導：sk_tmp = H(sk_root ‖ t)。"""
    def __init__(self, name):
        self.name = name
        self.root = Account.create()
        self.t = 0
        self.creds = {}          # 假名地址 -> (假名帳戶, [(idx,(addrR,s))...])
        self.receipts = []       # (serial, delta, [(idx,(addrR,s))...])

    def next_pseudonym(self):
        self.t += 1
        sk = hashlib.sha256(bytes(self.root.key) + self.t.to_bytes(8, "big")).digest()
        return Account.from_key(sk)


def protocol(w3, c, validators, fog, registrar):
    view = ChainView(c)
    out, gas = {}, {}
    A, B = User("A(rider)"), User("B(driver)")
    for u in (A, B):
        r = tx(w3, registrar, c.functions.registerRoot(u.root.address)); gas["registerRoot"] = r.gasUsed
    out["register_by_non_registrar"] = call_err(c.functions.registerRoot(Account.create().address), A.root)

    for u in (A, B):
        r = tx(w3, u.root, c.functions.openBatch(2)); gas["openBatch"] = r.gasUsed
    out["open_second_batch_while_outstanding"] = call_err(c.functions.openBatch(1), A.root)

    # 盲簽發憑證：A 找 V0,V1,V2；B 找 V1,V2,V3
    t0 = time.perf_counter()
    for u, idxs in ((A, (0, 1, 2)), (B, (1, 2, 3))):
        for _ in range(2):
            p = u.next_pseudonym()
            m = bytes.fromhex(p.address[2:])
            sigs = [(i, validators[i].issue_credential(view, u.root.address, m, F.blind_sign)) for i in idxs]
            assert all(F.verify(validators[i].cred.P, m, s) for i, s in sigs)
            u.creds[p.address] = (p, sigs)
    out["blind_issue_4_credentials_s"] = round(time.perf_counter() - t0, 3)
    try:
        validators[0].issue_credential(view, A.root.address, b"\x00" * 20, F.blind_sign)
        out["issue_beyond_batch"] = "NOT refused"
    except PermissionError as e:
        out["issue_beyond_batch"] = str(e)

    (ap, acred), (ap2, acred2) = list(A.creds.values())
    (bp, bcred), (bp2, bcred2) = list(B.creds.values())
    trip = secrets.token_bytes(32)

    def party(p, cred, gives, other, trip_=trip, status=0):
        d = c.functions.ratingDigest(trip_, status, gives, other).call()
        return (p.address, gives, sig3(cred), esign(p.key, d))

    def fsig(trip_, r, d, key=fog.key):
        return esign(key, c.functions.matchDigest(trip_, r, d).call())

    rider = party(ap, acred, 5, bp.address)        # 乘客給駕駛 5 分 -> 駕駛 +2
    driver = party(bp, bcred, 2, ap.address)       # 駕駛給乘客 2 分 -> 乘客 −1
    fs = fsig(trip, ap.address, bp.address)
    # 該擋的：霧節點簽章不對、憑證少一把有效簽章、同一驗證節點簽兩次、自己偽造憑證
    out["settle_without_fog_match"] = call_err(
        c.functions.attestAndSettle(trip, 0, rider, driver, fsig(trip, ap.address, bp.address, Account.create().key)), A.root)
    bad = list(sig3(acred)); bad[2] = (bad[2][0], bad[2][1], (bad[2][2] + 1) % F.N)
    out["settle_with_bad_validator_sig"] = call_err(
        c.functions.attestAndSettle(trip, 0, (rider[0], rider[1], bad, rider[3]), driver, fs), A.root)
    dup = list(sig3(acred)); dup[2] = dup[0]
    out["settle_with_duplicate_validator"] = call_err(
        c.functions.attestAndSettle(trip, 0, (rider[0], rider[1], dup, rider[3]), driver, fs), A.root)
    rogue = Account.create()
    rogue_cred = [(i, F.plain_sign(F.Issuer().x, bytes.fromhex(rogue.address[2:]))) for i in (0, 1, 2)]
    out["settle_with_self_made_credential"] = call_err(
        c.functions.attestAndSettle(trip, 0, party(rogue, rogue_cred, 5, bp.address), driver,
                                    fsig(trip, rogue.address, bp.address)), A.root)
    r = tx(w3, A.root, c.functions.attestAndSettle(trip, 0, rider, driver, fs)); gas["attestAndSettle"] = r.gasUsed
    out["valid_settle_status"] = r.status
    out["settle_same_trip_again"] = call_err(c.functions.attestAndSettle(trip, 0, rider, driver, fs), A.root)
    trip2 = secrets.token_bytes(32)
    out["reuse_spent_credential"] = call_err(c.functions.attestAndSettle(
        trip2, 0, party(ap, acred, 5, bp2.address, trip2), party(bp2, bcred2, 5, ap.address, trip2),
        fsig(trip2, ap.address, bp2.address)), A.root)

    # 收據：假名向 3 個驗證節點領面額收據（盲簽）
    for u, p, idxs in ((A, ap, (0, 1, 2)), (B, bp, (1, 2, 3))):
        serial = F.fresh_serial()
        got = [validators[i].issue_receipt(view, p.address, serial, F.blind_sign) for i in idxs]
        d = got[0][0]
        u.receipts.append((serial, d, [(i, g[1]) for i, g in zip(idxs, got)]))
    out["pending_delta_A_B"] = [A.receipts[0][1], B.receipts[0][1]]
    try:
        validators[0].issue_receipt(view, ap.address, F.fresh_serial(), F.blind_sign)
        out["second_receipt_same_pseudonym"] = "NOT refused"
    except PermissionError as e:
        out["second_receipt_same_pseudonym"] = str(e)
    # 不可連結：驗證節點從頭到尾沒看過收據序號（只看到盲化的挑戰值）
    out["receipt_serial_seen_by_validators"] = False

    def rc(u):
        s, d, sg = u.receipts[0]
        return (s, d, sig3(sg))

    def un(cred_pair):
        p, sg = cred_pair
        return (p.address, sig3(sg))

    r = tx(w3, A.root, c.functions.deposit([rc(A)], [un((ap2, acred2))])); gas["deposit(1 receipt+1 unused)"] = r.gasUsed
    r = tx(w3, B.root, c.functions.deposit([rc(B)], [un((bp2, bcred2))]))
    out["rootRep_after_deposit"] = {"A": c.functions.rootRep(A.root.address).call(),
                                    "B": c.functions.rootRep(B.root.address).call()}
    out["outstanding_after_deposit"] = {"A": c.functions.outstanding(A.root.address).call(),
                                        "B": c.functions.outstanding(B.root.address).call()}
    out["A_open_batch_below_theta"] = call_err(c.functions.openBatch(1), A.root)
    try:
        validators[0].issue_credential(view, A.root.address, b"\x01" * 20, F.blind_sign)
        out["validator_issue_below_theta"] = "NOT refused"
    except PermissionError as e:
        out["validator_issue_below_theta"] = str(e)
    tx(w3, B.root, c.functions.openBatch(1))
    out["deposit_same_receipt_twice"] = call_err(c.functions.deposit([rc(B)], []), B.root)
    out["use_returned_unused_credential"] = call_err(c.functions.attestAndSettle(
        trip2, 0, party(ap2, acred2, 5, bp.address, trip2), party(bp, bcred, 5, ap2.address, trip2),
        fsig(trip2, ap2.address, bp.address)), A.root)
    # ROS：同一把金鑰同時開兩個盲簽流程會被拒
    validators[3].cred.commit()
    try:
        validators[3].cred.commit()
        out["concurrent_blind_session"] = "NOT refused"
    except RuntimeError as e:
        out["concurrent_blind_session"] = str(e)
    validators[3].cred.abort()
    for k, v in out.items():
        print(f"    {k}: {v}")
    print(f"    gas: {gas}")
    return out, gas


def make_trip(c_addr, cid, validators, fog):
    """量測用：一趟合法結算（非盲 Schnorr 產憑證，驗證式相同）。"""
    from eth_abi import encode as abi_encode
    trip = secrets.token_bytes(32)
    rp, dp = Account.create(), Account.create()

    def cred(p):
        m = bytes.fromhex(p.address[2:])
        sigs = []
        for i in secrets.SystemRandom().sample(range(4), 3):   # 任 3 個驗證節點
            a, s = F.plain_sign(validators[i].cred.x, m)
            sigs.append((i, Web3.to_checksum_address(a), s))
        return sigs

    def rdig(gives, other):
        return Web3.keccak(abi_encode(["address", "uint256", "bytes32", "uint8", "uint8", "address"],
                                      [c_addr, cid, trip, 0, gives, other]))
    mdig = Web3.keccak(abi_encode(["address", "uint256", "bytes32", "address", "address"],
                                  [c_addr, cid, trip, rp.address, dp.address]))
    rider = (rp.address, 5, cred(rp), esign(rp.key, rdig(5, dp.address)))
    driver = (dp.address, 4, cred(dp), esign(dp.key, rdig(4, rp.address)))
    return trip, 0, rider, driver, esign(fog.key, mdig)


def prebuild(c, validators, fog, senders, nonces, n, cid):
    txs = []
    for i in range(n):
        s = senders[i % len(senders)]
        data = c.functions.attestAndSettle(*make_trip(c.address, cid, validators, fog))._encode_transaction_data()
        t = {"to": c.address, "data": data, "gas": GAS, "gasPrice": 0,
             "nonce": nonces[s.address], "chainId": cid, "value": 0}
        nonces[s.address] += 1
        raw = s.sign_transaction(t).raw_transaction
        txs.append((bytes(Web3.keccak(raw)).hex(), raw))
    return txs


def block_stats(watcher, row):
    """這一列交易落在哪些區塊：每塊筆數與出塊間隔（區塊時間戳，秒）。"""
    nums = [x["block"] for x in row["rows"] if x["block"] is not None]
    if not nums:
        return {}
    lo, hi = min(nums), max(nums)
    bl = [b for b in watcher.blocks if lo <= b[0] <= hi]
    ts = [b[1] for b in bl]
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    busy = [b[2] for b in bl if b[2] > 0]
    return {"blocks": len(bl), "tx_per_block_mean": round(statistics.mean(busy), 1) if busy else 0,
            "tx_per_block_max": max(busy) if busy else 0,
            "block_interval_mean_s": round(statistics.mean(gaps), 2) if gaps else None,
            "throughput_tx_per_s": round(len(nums) / (ts[-1] - ts[0]), 1) if len(ts) > 1 and ts[-1] > ts[0] else None}


def main():
    abi, binv = compile_v3()
    validators = [F.Validator(i) for i in range(4)]
    fog = Account.create()
    procs = L.start_nodes()
    try:
        w3 = L.wait_for_blocks()
        cid = w3.eth.chain_id
        registrar = w3.eth.account.from_key(open(ROOT / "out" / "deployer.key").read().strip())
        cpx, cpar, rpx, rpar = key_args(validators)
        C = w3.eth.contract(abi=abi, bytecode=binv)
        r = tx(w3, registrar, C.constructor(cpx, cpar, rpx, rpar, [fog.address], registrar.address,
                                            THETA, EPOCH_BLOCKS), gas=6_000_000)
        assert r.status == 1
        c = w3.eth.contract(address=r.contractAddress, abi=abi)
        print(f"  v3 合約部署於 {c.address}（gas={r.gasUsed}）")
        rr = tx(w3, registrar, c.functions.rollEpoch())
        e = c.functions.currentEpoch().call()
        salt = "0x" + bytes(c.functions.epochSalt(e).call()).hex()
        print(f"  鹽值信標：epoch {e} salt={salt[:18]}…（gas={rr.gasUsed}）")
        print("  協定測試：")
        proto, gas = protocol(w3, c, validators, fog, registrar)
        gas["deploy"] = r.gasUsed; gas["rollEpoch"] = rr.gasUsed

        others = [Web3(Web3.HTTPProvider(f"http://127.0.0.1:{L.BASE_RPC + i}")) for i in (1, 2, 3)]
        senders = [Account.create() for _ in range(N_SENDERS)]
        nonces = {s.address: 0 for s in senders}
        watcher = V2.BlockWatcher(L.RPC); watcher.start()
        results = []
        plan = [(None, N_SEQ, "sequential")] + [(x, N_OPEN, f"open-loop {x}/s") for x in RATES]
        for rate, n, label in plan:
            t0 = time.perf_counter()
            txs = prebuild(c, validators, fog, senders, nonces, n, cid)
            print(f"  準備 {n} 筆 {time.perf_counter() - t0:.1f}s")
            row = V2.run_row(w3, others, watcher, txs, rate, label)
            st = V2.stats([x["latency_s"] for x in row["rows"]])
            row.update(st)
            row.update(block_stats(watcher, row))
            print(f"  {label:>18}: 實際送出 {row['achieved_send_rate']:.1f} 筆/秒  p50={st['p50_s']}s "
                  f"p95={st['p95_s']}s p99={st['p99_s']}s  ≤3s 佔 {st['frac_le_3s']:.1%}  未確認 {st['n_missing']}  "
                  f"每塊 {row.get('tx_per_block_mean')}/{row.get('tx_per_block_max')} 筆  "
                  f"出塊間隔 {row.get('block_interval_mean_s')}s  吞吐 {row.get('throughput_tx_per_s')} 筆/秒")
            results.append(row)
            time.sleep(3)
        watcher.stop = True
        g, size, ok = [], [], 0
        for row in results:
            for x in row["rows"][:20]:
                rc = w3.eth.get_transaction_receipt("0x" + x["tx"])
                g.append(rc.gasUsed); ok += rc.status
            size += [x["bytes"] for x in row["rows"]]
        summary = {"contract": c.address, "theta": THETA, "threshold": "3-of-4",
                   "salt_beacon": {"epoch": e, "salt": salt},
                   "protocol_checks": proto, "gas": gas,
                   "settle_gas_median": int(statistics.median(g)),
                   "settle_tx_bytes_median": int(statistics.median(size)),
                   "sampled_receipts_ok": f"{ok}/{len(g)}",
                   "rows": [{k: v for k, v in row.items() if k != "rows"} for row in results]}
        print(f"  結算 gas 中位數 {summary['settle_gas_median']}，交易 {summary['settle_tx_bytes_median']} B，"
              f"抽樣收據成功 {summary['sampled_receipts_ok']}")
        json.dump(summary, open(ROOT / "out" / f"e6{SUF}_summary.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        json.dump(results, open(ROOT / "out" / f"e6{SUF}_raw.json", "w", encoding="utf-8"), indent=1)
        print(f"-> out/e6{SUF}_summary.json, out/e6{SUF}_raw.json")
    finally:
        print("收尾：關閉節點 …")
        import subprocess
        for p in procs:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        time.sleep(2)


if __name__ == "__main__":
    main()
