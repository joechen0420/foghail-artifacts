# -*- coding: utf-8 -*-
"""E6 量測 harness：對 4 節點 Besu QBFT 送 attestAndSettle 交易，量測
確認延遲 p50/p95、TPS 飽和點、鏈上 bytes/行程。需先 `docker compose up` 並
部署合約。此環境無 Besu/Docker，故本檔為可直接執行的量測腳本（待實跑）。

用法：
    pip install web3
    python bench_e6.py --rpc http://localhost:8545 --contract 0x... --tps 10
"""
import argparse
import time
import statistics
import secrets


def run(rpc, contract_addr, abi_path, key, tps, n):
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(rpc))
    acct = w3.eth.account.from_key(key)
    import json
    abi = json.load(open(abi_path))
    c = w3.eth.contract(address=Web3.to_checksum_address(contract_addr), abi=abi)

    lat, sizes = [], []
    interval = 1.0 / tps
    nonce = w3.eth.get_transaction_count(acct.address)
    for i in range(n):
        trip = secrets.token_bytes(32)
        rp = secrets.token_bytes(32); dp = secrets.token_bytes(32)
        tx = c.functions.attestAndSettle(trip, rp, dp, 1, 1).build_transaction({
            "from": acct.address, "nonce": nonce, "gasPrice": 0,
            "gas": 200000, "chainId": w3.eth.chain_id})
        signed = acct.sign_transaction(tx)
        t0 = time.perf_counter()
        h = w3.eth.send_raw_transaction(signed.raw_transaction)
        rcpt = w3.eth.wait_for_transaction_receipt(h, timeout=30)
        lat.append(time.perf_counter() - t0)
        sizes.append(len(signed.raw_transaction))
        nonce += 1
        time.sleep(max(0, interval - (time.perf_counter() - t0)))

    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(q * len(lat)))]
    print(f"TPS={tps} n={n}")
    print(f"  確認延遲 p50={p(.5):.3f}s p95={p(.95):.3f}s")
    print(f"  交易 raw bytes/行程 中位數={statistics.median(sizes):.0f}")
    return {"tps": tps, "conf_p50_s": p(.5), "conf_p95_s": p(.95),
            "tx_bytes": statistics.median(sizes)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", default="http://localhost:8545")
    ap.add_argument("--contract", required=True)
    ap.add_argument("--abi", default="out/FogHailAttestation.abi.json")
    ap.add_argument("--key", required=True, help="deployer private key")
    ap.add_argument("--tps", type=int, default=10)
    ap.add_argument("--n", type=int, default=200)
    a = ap.parse_args()
    run(a.rpc, a.contract, a.abi, a.key, a.tps, a.n)
