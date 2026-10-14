# -*- coding: utf-8 -*-
"""E6 v2（2026-10-14）：v2 合約＋開迴路送出＋逐筆存檔。

與 run_e6_local.py（v1，論文原 Table 8 的來源）差在三處：
1. 合約換 v2（雙方簽章、憑證序號防重用、ΔR 由合約算、鹽值信標）。先做四項「該擋的有擋」
   檢查（重複結算、重用憑證、偽造簽章、竄改評分），結果寫進輸出檔。
2. v1 的 bench() 每筆等確認完才送下一筆，標的 10/50/100 TPS 實際只有約 0.5 筆/秒。
   v2 改成開迴路：照目標速率送出，另一條執行緒盯新區塊記錄每筆第一次出現在鏈上的時間。
   另保留一列「sequential」（逐筆等確認，同 v1 作法）供對照。
3. 每一筆的送出時間、上鏈時間、區塊號、gas 全部存檔（out/e6_v2_raw.json），可算任意分位數
   與「幾成在 3 秒內確認」。

啟動方式（CPU 隔離、1 s 出塊，同論文設定）：
  FOGHAIL_NETDIR=networkFiles1s FOGHAIL_AFFINITY=1 FOGHAIL_SUF=_v2 python run_e6_v2.py
"""
import os
import sys
import json
import time
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import run_e6_local as L  # noqa: E402  沿用起節點／等出塊／收尾

from web3 import Web3                         # noqa: E402
from eth_account import Account               # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402
from eth_abi import encode as abi_encode      # noqa: E402

EPOCH_BLOCKS = 3600            # 1 s 出塊 × 3600 = 1 h epoch（Section 6.1 預設）
N_SEQ = 200                    # 逐筆等確認（v1 作法）
RATES = (10, 50, 100)          # 開迴路目標送出速率（筆/秒）
N_OPEN = 300                   # 每個速率的筆數
N_SENDERS = 8                  # 提交帳戶數（霧節點代送；gasPrice=0 不需餘額）
GAS = 400_000
SUF = os.environ.get("FOGHAIL_SUF", "_v2")


def compile_v2():
    import solcx
    src = (ROOT / "contracts" / "FogHailAttestation.sol").read_text(encoding="utf-8")
    out = solcx.compile_standard({
        "language": "Solidity", "sources": {"F.sol": {"content": src}},
        "settings": {"evmVersion": "berlin", "optimizer": {"enabled": True, "runs": 200},
                     "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}}}},
        solc_version="0.8.19")
    c = out["contracts"]["F.sol"]["FogHailAttestation"]
    abi, binv = c["abi"], c["evm"]["bytecode"]["object"]
    json.dump(abi, open(ROOT / "out" / "FogHailAttestation_v2.abi.json", "w"), indent=1)
    (ROOT / "out" / "FogHailAttestation_v2.bin").write_text(binv)
    return abi, binv


def deploy(w3, abi, binv):
    key = open(ROOT / "out" / "deployer.key").read().strip()
    acct = w3.eth.account.from_key(key)
    C = w3.eth.contract(abi=abi, bytecode=binv)
    tx = C.constructor(EPOCH_BLOCKS).build_transaction({
        "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": 3_000_000, "gasPrice": 0, "chainId": w3.eth.chain_id})
    h = w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
    r = w3.eth.wait_for_transaction_receipt(h, timeout=60)
    assert r.status == 1, "部署失敗"
    print(f"  v2 合約部署於 {r.contractAddress}（gas={r.gasUsed}）")
    return acct, w3.eth.contract(address=r.contractAddress, abi=abi)


def send_and_wait(w3, acct, fn):
    tx = fn.build_transaction({"from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address),
                               "gas": GAS, "gasPrice": 0, "chainId": w3.eth.chain_id})
    h = w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
    return w3.eth.wait_for_transaction_receipt(h, timeout=60)


class TripMaker:
    """產生一趟行程的結算參數：兩把假名金鑰、兩張憑證序號、兩方簽章。"""
    def __init__(self, contract_addr, chain_id):
        self.addr, self.cid = contract_addr, chain_id

    def digest(self, trip, status, rating, counterpart, cred):
        return Web3.keccak(abi_encode(
            ["address", "uint256", "bytes32", "uint8", "uint8", "address", "bytes32"],
            [self.addr, self.cid, trip, status, rating, counterpart, cred]))

    def sign(self, key, d):
        return bytes(Account.sign_message(encode_defunct(primitive=d), key).signature)

    def make(self, status=0, r_gives=5, d_gives=4):
        trip = secrets.token_bytes(32)
        rk, dk = Account.create(), Account.create()       # 本趟／本班假名
        rc, dc = secrets.token_bytes(32), secrets.token_bytes(32)   # 一次性憑證序號
        rsig = self.sign(rk.key, self.digest(trip, status, r_gives, dk.address, rc))
        dsig = self.sign(dk.key, self.digest(trip, status, d_gives, rk.address, dc))
        return trip, status, (rk.address, r_gives, rc, rsig), (dk.address, d_gives, dc, dsig)


def reverts(c, sender, args):
    """以 eth_call 模擬，回傳 revert 原因；沒 revert 回 None。"""
    try:
        c.functions.attestAndSettle(*args).call({"from": sender, "gas": GAS})
        return None
    except Exception as e:
        return str(e)[:120]


def checks(w3, acct, c, tm):
    """四項防護檢查：每項都應被合約擋下。"""
    out = {}
    args = tm.make()
    r = send_and_wait(w3, acct, c.functions.attestAndSettle(*args))
    out["valid_settle_status"] = r.status
    out["duplicate_trip"] = reverts(c, acct.address, args)
    # 重用憑證：新行程、新簽章，但乘客沿用剛才那張憑證序號
    trip, st, rp, dp = tm.make()
    rk = Account.create()
    reused = args[2][2]
    rsig = tm.sign(rk.key, tm.digest(trip, st, rp[1], dp[0], reused))
    out["reused_credential"] = reverts(c, acct.address, (trip, st, (rk.address, rp[1], reused, rsig), dp))
    # 偽造簽章：提交者用自己的金鑰冒充乘客
    trip, st, rp, dp = tm.make()
    fake = tm.sign(Account.create().key, tm.digest(trip, st, rp[1], dp[0], rp[2]))
    out["forged_signature"] = reverts(c, acct.address, (trip, st, (rp[0], rp[1], rp[2], fake), dp))
    # 竄改評分：簽的是 5 分，送出時改成 1 分
    trip, st, rp, dp = tm.make()
    out["tampered_rating"] = reverts(c, acct.address, (trip, st, (rp[0], 1, rp[2], rp[3]), dp))
    rep_driver = c.functions.reputation(args[3][0]).call()
    rep_rider = c.functions.reputation(args[2][0]).call()
    out["reputation_after_valid"] = {"driver(+rating 5)": rep_driver, "rider(+rating 4)": rep_rider}
    for k, v in out.items():
        print(f"    {k}: {v}")
    return out


class BlockWatcher(threading.Thread):
    """盯新區塊，記下每筆交易第一次出現在鏈上的本機時間。"""
    def __init__(self, rpc):
        super().__init__(daemon=True)
        self.w3 = Web3(Web3.HTTPProvider(rpc))
        self.seen, self.block_of = {}, {}
        self.blocks = []           # (區塊號, 區塊時間戳, 筆數, gasUsed)
        self.stop = False
        self.last = self.w3.eth.block_number

    def run(self):
        while not self.stop:
            try:
                bn = self.w3.eth.block_number
                while self.last < bn:
                    # 直接走原始 RPC：QBFT 的 extraData 超過 32 B，web3 的 get_block 會丟例外
                    b = self.w3.provider.make_request("eth_getBlockByNumber", [hex(self.last + 1), False])["result"]
                    if b is None:          # 節點還沒備好這一塊，下一輪再抓，不能跳過
                        break
                    self.last += 1
                    now = time.perf_counter()
                    self.blocks.append((self.last, int(b["timestamp"], 16), len(b["transactions"]),
                                        int(b["gasUsed"], 16)))
                    for h in b["transactions"]:
                        hx = h[2:] if h.startswith("0x") else h
                        self.seen.setdefault(hx, now)
                        self.block_of.setdefault(hx, self.last)
            except Exception as ex:
                print(f"  [watcher] {ex}", flush=True)
            time.sleep(0.02)


def prebuild(c, tm, senders, nonces, n, chain_id):
    txs = []
    for i in range(n):
        s = senders[i % len(senders)]
        data = c.functions.attestAndSettle(*tm.make())._encode_transaction_data()
        tx = {"to": c.address, "data": data, "gas": GAS, "gasPrice": 0,
              "nonce": nonces[s.address], "chainId": chain_id, "value": 0}
        nonces[s.address] += 1
        raw = s.sign_transaction(tx).raw_transaction
        txs.append((bytes(Web3.keccak(raw)).hex(), raw))
    return txs


def run_row(w3, others, watcher, txs, rate, label):
    # 每個節點一條專屬執行緒、照送出順序轉送：平行轉送會打亂同一帳戶的 nonce 順序，
    # 其他驗證節點只能把亂序交易擱著，出塊時幾乎是空的（2026-10-14 第一次量測踩到）。
    pools = [ThreadPoolExecutor(max_workers=1) for _ in others]
    sent = {}
    interval = (1.0 / rate) if rate else None
    t_start = time.perf_counter()
    for i, (hx, raw) in enumerate(txs):
        if interval:
            target = t_start + i * interval
            dt = target - time.perf_counter()
            if dt > 0:
                time.sleep(dt)
        t0 = time.perf_counter()
        w3.eth.send_raw_transaction(raw)
        sent[hx] = t0
        for o, pl in zip(others, pools):
            pl.submit(_quiet, o.eth.send_raw_transaction, raw)
        if not interval:                                   # sequential：等這筆上鏈再送下一筆
            dl = time.time() + 60
            while hx not in watcher.seen and time.time() < dl:
                time.sleep(0.005)
    t_send = time.perf_counter() - t_start
    deadline = time.time() + 120
    while time.time() < deadline and any(h not in watcher.seen for h in sent):
        time.sleep(0.1)
    for pl in pools:
        pl.shutdown(wait=True)
    rows = []
    size = {hx: len(raw) for hx, raw in txs}
    for hx, t0 in sent.items():
        rows.append({"tx": hx, "latency_s": (watcher.seen[hx] - t0) if hx in watcher.seen else None,
                     "block": watcher.block_of.get(hx), "bytes": size[hx]})
    achieved = len(txs) / t_send if t_send > 0 else None
    return {"label": label, "target_rate": rate, "achieved_send_rate": achieved, "rows": rows}


def _quiet(f, *a):
    try:
        f(*a)
    except Exception:
        pass


def stats(lat):
    import numpy as np
    a = np.array([x for x in lat if x is not None])
    return {"n_confirmed": int(a.size), "n_missing": int(sum(x is None for x in lat)),
            "p50_s": round(float(np.percentile(a, 50)), 3), "p95_s": round(float(np.percentile(a, 95)), 3),
            "p99_s": round(float(np.percentile(a, 99)), 3), "max_s": round(float(a.max()), 3),
            "frac_le_3s": round(float(np.mean(a <= 3.0)), 4)}


def main():
    abi, binv = compile_v2()
    procs = L.start_nodes()
    try:
        w3 = L.wait_for_blocks()
        cid = w3.eth.chain_id
        acct, c = deploy(w3, abi, binv)
        r = send_and_wait(w3, acct, c.functions.rollEpoch())
        e = c.functions.currentEpoch().call()
        salt = c.functions.epochSalt(e).call().hex()
        print(f"  鹽值信標：epoch {e} salt = 0x{salt[:16]}…（rollEpoch gas={r.gasUsed}）")
        again = None
        try:
            c.functions.rollEpoch().call({"from": acct.address})
        except Exception as ex:
            again = str(ex)[:80]
        tm = TripMaker(c.address, cid)
        print("  防護檢查：")
        chk = checks(w3, acct, c, tm)

        others = [Web3(Web3.HTTPProvider(f"http://127.0.0.1:{L.BASE_RPC + i}")) for i in (1, 2, 3)]
        senders = [Account.create() for _ in range(N_SENDERS)]
        nonces = {s.address: 0 for s in senders}
        watcher = BlockWatcher(L.RPC); watcher.start()

        results = []
        plan = [(None, N_SEQ, "sequential")] + [(r_, N_OPEN, f"open-loop {r_}/s") for r_ in RATES]
        for rate, n, label in plan:
            txs = prebuild(c, tm, senders, nonces, n, cid)
            row = run_row(w3, others, watcher, txs, rate, label)
            st = stats([x["latency_s"] for x in row["rows"]])
            row.update(st)
            print(f"  {label:>18}: 實際送出 {row['achieved_send_rate']:.1f} 筆/秒  p50={st['p50_s']}s "
                  f"p95={st['p95_s']}s p99={st['p99_s']}s  ≤3s 佔 {st['frac_le_3s']:.1%}  "
                  f"未確認 {st['n_missing']}")
            results.append(row)
            time.sleep(3)
        watcher.stop = True

        # gas 與交易大小：抽每列前 20 筆收據
        gas, size, ok = [], [], 0
        for row in results:
            for x in row["rows"][:20]:
                rc = w3.eth.get_transaction_receipt("0x" + x["tx"])
                gas.append(rc.gasUsed); ok += rc.status
                size.append(len(w3.eth.get_raw_transaction("0x" + x["tx"])))
        import statistics
        summary = {
            "contract": c.address, "epoch_blocks": EPOCH_BLOCKS,
            "salt_beacon": {"epoch": e, "salt": "0x" + salt, "roll_gas": r.gasUsed,
                            "second_roll_same_epoch": again},
            "checks": chk,
            "gas_median": int(statistics.median(gas)), "tx_bytes_median": int(statistics.median(size)),
            "sampled_receipts_ok": f"{ok}/{len(gas)}",
            "rows": [{k: v for k, v in row.items() if k != "rows"} for row in results],
        }
        print(f"  gas 中位數 {summary['gas_median']}，交易大小 {summary['tx_bytes_median']} B，"
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
