# -*- coding: utf-8 -*-
"""多主機 E6 量測：連到 4 台各自主機上的 Besu 節點 RPC，部署合約並量測
確認延遲 p50/p95 與 TPS 飽和。交易廣播到全部 4 節點池（模擬真實傳播）。

用法（在任一台能連到 4 節點 RPC 的機器）：
    pip install web3 py-solc-x
    python bench_e6_cloud.py \
        --rpcs http://10.0.1.11:8545 http://10.0.1.12:8545 http://10.0.1.13:8545 http://10.0.1.14:8545 \
        --key <deployer_private_key_hex> --block-period 1

先確認 4 節點已互聯出塊（見多主機部署文件）。合約 abi/bin 取自 out/。
"""
import argparse
import time
import json
import secrets
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def connect(rpcs):
    from web3 import Web3
    ws = [Web3(Web3.HTTPProvider(u, request_kwargs={"timeout": 30})) for u in rpcs]
    for u, w in zip(rpcs, ws):
        assert w.is_connected(), f"連不到 {u}"
    return ws


def deploy(w3, key):
    acct = w3.eth.account.from_key(key)
    abi = json.load(open(ROOT / "out" / "FogHailAttestation.abi.json"))
    binv = open(ROOT / "out" / "FogHailAttestation.bin").read().strip()
    C = w3.eth.contract(abi=abi, bytecode=binv)
    nonce = w3.eth.get_transaction_count(acct.address)
    tx = C.constructor().build_transaction({"from": acct.address, "nonce": nonce,
        "gas": 1_500_000, "gasPrice": 0, "chainId": w3.eth.chain_id})
    s = acct.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(s.raw_transaction)
    r = w3.eth.wait_for_transaction_receipt(h, timeout=60)
    print(f"合約部署於 {r.contractAddress}（gas={r.gasUsed}）")
    return acct, r.contractAddress, abi


def bench_latency(ws, acct, addr, abi, tps, n):
    """確認延遲：循序送、廣播到全部節點、等收據。"""
    w3 = ws[0]; others = ws[1:]
    c = w3.eth.contract(address=addr, abi=abi)
    lat, sizes, gas = [], [], []
    interval = 1.0 / tps
    nonce = w3.eth.get_transaction_count(acct.address)
    for _ in range(n):
        loop = time.perf_counter()
        args = (secrets.token_bytes(32), secrets.token_bytes(32), secrets.token_bytes(32), 1, 1)
        tx = c.functions.attestAndSettle(*args).build_transaction({
            "from": acct.address, "nonce": nonce, "gas": 250000, "gasPrice": 0,
            "chainId": w3.eth.chain_id})
        s = acct.sign_transaction(tx)
        t0 = time.perf_counter()
        h = w3.eth.send_raw_transaction(s.raw_transaction)
        for o in others:
            try: o.eth.send_raw_transaction(s.raw_transaction)
            except Exception: pass
        r = w3.eth.wait_for_transaction_receipt(h, timeout=30)
        lat.append(time.perf_counter() - t0)
        sizes.append(len(s.raw_transaction)); gas.append(r.gasUsed)
        nonce += 1
        dt = time.perf_counter() - loop
        if dt < interval: time.sleep(interval - dt)
    lat.sort()
    q = lambda p: lat[min(len(lat)-1, int(p*len(lat)))]
    return {"tps": tps, "n": n, "conf_p50_s": round(q(.5),3), "conf_p95_s": round(q(.95),3),
            "tx_bytes": int(statistics.median(sizes)), "gas": int(statistics.median(gas))}


def bench_throughput(ws, acct, addr, abi, burst):
    """TPS 飽和：一次性送出 burst 筆（不等收據），量全部確認所需時間 → 吞吐。"""
    w3 = ws[0]; others = ws[1:]
    c = w3.eth.contract(address=addr, abi=abi)
    nonce = w3.eth.get_transaction_count(acct.address)
    hashes = []
    t0 = time.perf_counter()
    for _ in range(burst):
        args = (secrets.token_bytes(32), secrets.token_bytes(32), secrets.token_bytes(32), 1, 1)
        tx = c.functions.attestAndSettle(*args).build_transaction({
            "from": acct.address, "nonce": nonce, "gas": 250000, "gasPrice": 0,
            "chainId": w3.eth.chain_id})
        s = acct.sign_transaction(tx)
        h = w3.eth.send_raw_transaction(s.raw_transaction)
        for o in others:
            try: o.eth.send_raw_transaction(s.raw_transaction)
            except Exception: pass
        hashes.append(h); nonce += 1
    for h in hashes:
        w3.eth.wait_for_transaction_receipt(h, timeout=120)
    dt = time.perf_counter() - t0
    return {"burst": burst, "elapsed_s": round(dt, 2), "throughput_tps": round(burst/dt, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpcs", nargs=4, required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--block-period", type=int, default=1)
    a = ap.parse_args()
    ws = connect(a.rpcs)
    print(f"已連 4 節點，chainId={ws[0].eth.chain_id}，出塊={a.block_period}s")
    acct, addr, abi = deploy(ws[0], a.key)
    out = {"block_period_s": a.block_period, "latency": [], "throughput": []}
    for tps in (10, 50, 100):
        r = bench_latency(ws, acct, addr, abi, tps, n=60)
        print(f"[延遲] TPS={tps}: p50={r['conf_p50_s']}s p95={r['conf_p95_s']}s gas={r['gas']}")
        out["latency"].append(r)
    for burst in (100, 300, 600):
        r = bench_throughput(ws, acct, addr, abi, burst)
        print(f"[吞吐] burst={burst}: {r['elapsed_s']}s → {r['throughput_tps']} tx/s")
        out["throughput"].append(r)
    json.dump(out, open(ROOT / "out" / "e6_cloud_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"-> {ROOT/'out'/'e6_cloud_results.json'}")


if __name__ == "__main__":
    main()
