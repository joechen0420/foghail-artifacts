# -*- coding: utf-8 -*-
"""E6 v4（2026-10-14）：v4 合約的端到端協定測試（含 Code_Audit_2026-10-14 的對抗測試）＋確認延遲量測。

第一部分 protocol：在活的 4 節點 QBFT 鏈上把 v4 協定完整走一次。驗證節點用 foghail_cred.Validator
  （只收盲化值與授權簽章、狀態落地），每個部分簽章都先 logIssue / logReceipt 上鏈記帳。
  逐項確認該擋的有擋：P0-1 第 3B+1 個部分簽章、負評收據不交就開不了新批次；
  P0-2 錯的根簽章、非驗證節點記帳、拿別人的假名領收據；P0-3 第 4 個節點發收據、驗證節點重啟後再發；
  P1 存別人的收據、搶先交回別人的未用憑證；以及 v3 原有的結算檢查。另記錄每個操作的 gas。
第二部分 latency：與 run_e6_v3.py 相同的量測法（attestAndSettle 未改），在 v4 合約上重量一次。
  FOGHAIL_LATENCY=0 時只跑第一部分。

  FOGHAIL_NETDIR=networkFiles1s FOGHAIL_AFFINITY=1 FOGHAIL_SUF=_v4 python -u run_e6_v4.py
"""
import os
import sys
import json
import time
import secrets
import statistics
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "phase5"))
import run_e6_local as L          # noqa: E402
import run_e6_v2 as V2            # noqa: E402  BlockWatcher / run_row / stats
import foghail_cred as F          # noqa: E402  v4

from web3 import Web3                            # noqa: E402
from eth_account import Account                  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402

EPOCH_BLOCKS = 3600
THETA = 0
N_SEQ, RATES, N_OPEN, N_SENDERS = 200, (5, 10, 20, 50), 300, 8
GAS = 1_000_000
SUF = os.environ.get("FOGHAIL_SUF", "_v4")
LATENCY = os.environ.get("FOGHAIL_LATENCY", "1") != "0"


def compile_v4():
    import solcx
    src = (ROOT / "contracts" / "FogHailAttestation.sol").read_text(encoding="utf-8")
    out = solcx.compile_standard({
        "language": "Solidity", "sources": {"F.sol": {"content": src}},
        "settings": {"evmVersion": "berlin", "viaIR": True, "optimizer": {"enabled": True, "runs": 200},
                     "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}}}},
        solc_version="0.8.19")
    c = out["contracts"]["F.sol"]["FogHailAttestation"]
    json.dump(c["abi"], open(ROOT / "out" / "FogHailAttestation_v4.abi.json", "w"), indent=1)
    (ROOT / "out" / "FogHailAttestation_v4.bin").write_text(c["evm"]["bytecode"]["object"])
    return c["abi"], c["evm"]["bytecode"]["object"]


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


def esign(key, digest):
    return bytes(Account.sign_message(encode_defunct(primitive=digest), key).signature)


def cs(a):
    return Web3.to_checksum_address(a)


class ChainLedger:
    """foghail_cred.Validator 用的鏈上帳：讀狀態用 call，記帳用驗證節點自己的帳戶送交易。"""
    def __init__(self, w3, c):
        self.w3, self.c, self.f = w3, c, c.functions
        self.contract, self.chain_id = c.address, w3.eth.chain_id
        self.gas = {"logIssue": [], "logReceipt": []}

    def can_issue(self, root):
        r = cs(root)
        return self.f.registered(r).call() and self.f.batchIssued(r).call() < self.f.batchBudget(r).call()

    def batch_nonce(self, root):
        return self.f.batchNonce(cs(root)).call()

    def session_logged(self, h):
        return self.f.sessionLogged(h).call()

    def pending_delta(self, p):
        p = cs(p)
        return self.f.pendingDelta(p).call() if self.f.hasPending(p).call() else None

    def can_receipt(self, p, idx):
        mask = self.f.receiptMask(cs(p)).call()
        return not (mask >> idx) & 1 and bin(mask).count("1") < F.T

    def _log(self, validator, fn, name):
        err = call_err(fn, validator.account)
        if err:
            raise PermissionError(err)
        r = tx(self.w3, validator.account, fn)
        if r.status != 1:
            raise PermissionError(f"{name} reverted")
        self.gas[name].append(r.gasUsed)

    def log_issue(self, validator, root, h, auth):
        self._log(validator, self.f.logIssue(cs(root), h, auth), "logIssue")

    def log_receipt(self, validator, p, h, auth):
        self._log(validator, self.f.logReceipt(cs(p), h, auth), "logReceipt")


def key_args(validators):
    cpx = [int(v.cred.P.x()) for v in validators]
    cpar = [int(v.cred.P.y()) & 1 for v in validators]
    rpx, rpar = [], []
    for d in F.DELTAS:                       # [ΔR+2][驗證節點] 攤平成 d*4+v
        for v in validators:
            P = v.receipt[d].P
            rpx.append(int(P.x())); rpar.append(int(P.y()) & 1)
    return cpx, cpar, rpx, rpar, [v.account.address for v in validators]


def sig3(sigs):
    return [(i, cs(a), s) for i, (a, s) in sigs]


def refused(fn):
    try:
        fn()
    except (PermissionError, RuntimeError) as e:
        return str(e)[:70]
    return "NOT refused"


def protocol(w3, c, validators, fog, registrar, ledger, store_dir):
    out, gas = {}, {}
    f = c.functions
    A, B = Account.create(), Account.create()          # A 乘客、B 駕駛的根身分
    for u in (A, B):
        r = tx(w3, registrar, f.registerRoot(u.address)); gas["registerRoot"] = r.gasUsed
    out["register_by_non_registrar"] = call_err(f.registerRoot(Account.create().address), A)
    r = tx(w3, A, f.openBatch(3)); gas["openBatch"] = r.gasUsed
    tx(w3, B, f.openBatch(1))

    def cred(owner, idxs):
        p = Account.create()
        return p, F.obtain_credential([validators[i] for i in idxs], ledger, owner, bytes.fromhex(p.address[2:]))

    # ---- P0-2：記帳要根身分本人授權、要由登記的驗證節點送
    h = secrets.token_bytes(32)
    bad = F.esign(Account.create().key, f.authDigest(F.KIND_CRED, f.batchNonce(B.address).call(), 0, h).call())
    out["P0-2_logIssue_wrong_root_key"] = call_err(f.logIssue(B.address, h, bad), validators[0].account)
    out["P0-2_logIssue_by_non_validator"] = call_err(f.logIssue(B.address, h, bad), A)
    bp, bc = cred(B, (1, 2, 3))

    # ---- P0-1：稽核反例 B=3、子集 (0,1,2)(0,1,3)(0,2,3)(1,2,3)
    t0 = time.perf_counter()
    a = [cred(A, s) for s in [(0, 1, 2), (0, 1, 3), (0, 2, 3)]]
    out["blind_issue_3_credentials_s"] = round(time.perf_counter() - t0, 2)
    out["P0-1_fourth_credential_validator"] = refused(lambda: cred(A, (1, 2, 3)))
    au = F.esign(A.key, f.authDigest(F.KIND_CRED, f.batchNonce(A.address).call(), 1, h).call())
    out["P0-1_fourth_credential_onchain"] = call_err(f.logIssue(A.address, h, au), validators[1].account)
    out["A_outstanding_units_after_issue"] = f.outstanding(A.address).call()
    out["open_second_batch_while_outstanding"] = call_err(f.openBatch(1), A)

    # ---- 結算（v3 原有檢查）
    trip = secrets.token_bytes(32)
    (ap, ac), (ap2, ac2), (ap3, ac3) = a

    def party(p, cr, gives, other, trip_=trip, status=0):
        d = f.ratingDigest(trip_, status, gives, other).call()
        return (p.address, gives, sig3(cr), F.esign(p.key, d))

    def fsig(trip_, r_, d_, key=fog.key):
        return F.esign(key, f.matchDigest(trip_, r_, d_).call())

    rider = party(ap, ac, 5, bp.address)            # 乘客給駕駛 5 分 -> 駕駛 +2
    driver = party(bp, bc, 1, ap.address)           # 駕駛給乘客 1 分 -> 乘客 −2
    fs = fsig(trip, ap.address, bp.address)
    out["settle_without_fog_match"] = call_err(
        f.attestAndSettle(trip, 0, rider, driver, fsig(trip, ap.address, bp.address, Account.create().key)), A)
    badc = list(sig3(ac)); badc[2] = (badc[2][0], badc[2][1], (badc[2][2] + 1) % F.N)
    out["settle_with_bad_validator_sig"] = call_err(
        f.attestAndSettle(trip, 0, (rider[0], rider[1], badc, rider[3]), driver, fs), A)
    dup = list(sig3(ac)); dup[2] = dup[0]
    out["settle_with_duplicate_validator"] = call_err(
        f.attestAndSettle(trip, 0, (rider[0], rider[1], dup, rider[3]), driver, fs), A)
    rogue = Account.create()
    rogue_cred = [(i, F.plain_sign(F.Issuer().x, bytes.fromhex(rogue.address[2:]))) for i in (0, 1, 2)]
    out["settle_with_self_made_credential"] = call_err(
        f.attestAndSettle(trip, 0, party(rogue, rogue_cred, 5, bp.address), driver,
                          fsig(trip, rogue.address, bp.address)), A)
    r = tx(w3, A, f.attestAndSettle(trip, 0, rider, driver, fs)); gas["attestAndSettle"] = r.gasUsed
    out["valid_settle_status"] = r.status
    out["settle_same_trip_again"] = call_err(f.attestAndSettle(trip, 0, rider, driver, fs), A)
    trip2 = secrets.token_bytes(32)
    out["reuse_spent_credential"] = call_err(f.attestAndSettle(
        trip2, 0, party(ap, ac, 5, ap2.address, trip2), party(ap2, ac2, 5, ap.address, trip2),
        fsig(trip2, ap.address, ap2.address)), A)

    # ---- P0-2：知道別人已結算的假名、用自己的金鑰申請收據
    thief = Account.create()
    h2 = secrets.token_bytes(32)
    out["P0-2_logReceipt_by_non_holder"] = call_err(
        f.logReceipt(bp.address, h2, F.esign(thief.key, f.authDigest(F.KIND_RCPT, 0, 0, h2).call())),
        validators[0].account)
    # ---- P1：搶先把 A 的未用憑證交回到 B
    out["P1_front_run_unused_return"] = call_err(
        f.deposit([], [(ap2.address, sig3(ac2), F.return_proof(ledger, ap2, A.address))]), B)
    # ---- 負評不能丟：A 只交回兩張未用憑證
    r = tx(w3, A, f.deposit([], [(p.address, sig3(s), F.return_proof(ledger, p, A.address)) for p, s in a[1:]]))
    gas["deposit(2 unused)"] = r.gasUsed
    out["P0-1_outstanding_without_negative_receipt"] = f.outstanding(A.address).call()
    out["P0-1_open_batch_without_negative_receipt"] = call_err(f.openBatch(3), A)
    # ---- 收據
    t0 = time.perf_counter()
    rA = F.obtain_receipt(validators[:3], ledger, ap, A.address)
    rB = F.obtain_receipt(validators[1:], ledger, bp, B.address)
    out["blind_receipts_2_s"] = round(time.perf_counter() - t0, 2)
    out["pending_delta_A_B"] = [rA[1], rB[1]]
    out["P0-3_fourth_validator_receipt"] = refused(lambda: validators[3].rcpt_commit(ap.address))
    h3 = secrets.token_bytes(32)
    out["P0-3_fourth_validator_receipt_onchain"] = call_err(
        f.logReceipt(ap.address, h3, F.esign(ap.key, f.authDigest(F.KIND_RCPT, 0, 3, h3).call())),
        validators[3].account)
    v0b = F.Validator(0, ledger, store_path=Path(store_dir) / "v0.json", keys=validators[0].keys(),
                      account=validators[0].account)
    out["P0-3_second_receipt_after_restart"] = refused(lambda: v0b.rcpt_commit(ap.address))

    def rc(x):
        return (x[0], x[1], sig3(x[2]))
    out["P1_deposit_others_receipt"] = call_err(f.deposit([rc(rA)], []), B)
    r = tx(w3, A, f.deposit([rc(rA)], [])); gas["deposit(1 receipt)"] = r.gasUsed
    tx(w3, B, f.deposit([rc(rB)], []))
    out["rootRep_after_deposit"] = {"A": f.rootRep(A.address).call(), "B": f.rootRep(B.address).call()}
    out["outstanding_after_deposit"] = {"A": f.outstanding(A.address).call(), "B": f.outstanding(B.address).call()}
    out["A_open_batch_below_theta"] = call_err(f.openBatch(1), A)
    out["deposit_same_receipt_twice"] = call_err(f.deposit([rc(rA)], []), A)
    out["use_returned_unused_credential"] = call_err(f.attestAndSettle(
        trip2, 0, party(ap2, ac2, 5, bp.address, trip2), party(bp, bc, 5, ap2.address, trip2),
        fsig(trip2, ap2.address, bp.address)), A)
    tx(w3, B, f.openBatch(1))
    out["B_reopen_after_clearing"] = f.batchNonce(B.address).call() == 2
    # ---- ROS：同一把金鑰同時開兩個盲簽會談
    validators[3].cred.commit("x")
    out["concurrent_blind_session"] = refused(lambda: validators[3].cred.commit("y"))
    validators[3].cred.abort()
    gas["logIssue_median"] = int(statistics.median(ledger.gas["logIssue"]))
    gas["logReceipt_median"] = int(statistics.median(ledger.gas["logReceipt"]))
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
    abi, binv = compile_v4()
    store_dir = tempfile.mkdtemp(prefix="foghail_v4_validators_")
    validators = [F.Validator(i, store_path=Path(store_dir) / f"v{i}.json") for i in range(4)]
    fog = Account.create()
    procs = L.start_nodes()
    try:
        w3 = L.wait_for_blocks()
        cid = w3.eth.chain_id
        registrar = w3.eth.account.from_key(open(ROOT / "out" / "deployer.key").read().strip())
        cpx, cpar, rpx, rpar, vaddr = key_args(validators)
        C = w3.eth.contract(abi=abi, bytecode=binv)
        r = tx(w3, registrar, C.constructor(cpx, cpar, rpx, rpar, vaddr, [fog.address], registrar.address,
                                            THETA, EPOCH_BLOCKS), gas=6_000_000)
        assert r.status == 1
        c = w3.eth.contract(address=r.contractAddress, abi=abi)
        print(f"  v4 合約部署於 {c.address}（gas={r.gasUsed}）")
        rr = tx(w3, registrar, c.functions.rollEpoch())
        e = c.functions.currentEpoch().call()
        salt = "0x" + bytes(c.functions.epochSalt(e).call()).hex()
        print(f"  鹽值信標：epoch {e} salt={salt[:18]}…（gas={rr.gasUsed}）")
        print("  協定測試：")
        ledger = ChainLedger(w3, c)
        for v in validators:
            v.ledger = ledger
        proto, gas = protocol(w3, c, validators, fog, registrar, ledger, store_dir)
        gas["deploy"] = r.gasUsed; gas["rollEpoch"] = rr.gasUsed

        others = [Web3(Web3.HTTPProvider(f"http://127.0.0.1:{L.BASE_RPC + i}")) for i in (1, 2, 3)]
        senders = [Account.create() for _ in range(N_SENDERS)]
        nonces = {s.address: 0 for s in senders}
        watcher = V2.BlockWatcher(L.RPC); watcher.start()
        results = []
        plan = ([(None, N_SEQ, "sequential")] + [(x, N_OPEN, f"open-loop {x}/s") for x in RATES]) if LATENCY else []
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
        summary = {"contract": c.address, "theta": THETA, "threshold": "3-of-4", "issuance": "on-chain budget T*B, holder-authorized, logged per partial",
                   "salt_beacon": {"epoch": e, "salt": salt},
                   "protocol_checks": proto, "gas": gas,
                   "settle_gas_median": int(statistics.median(g)) if g else gas["attestAndSettle"],
                   "settle_tx_bytes_median": int(statistics.median(size)) if size else None,
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
