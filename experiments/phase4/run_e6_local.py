# -*- coding: utf-8 -*-
"""單機啟動 4 節點 Besu QBFT、部署 FogHailAttestation、量測 E6。
不需 Docker：直接用 Java 21 執行 Besu 25.4.1。

流程：起 4 節點 -> 等出塊 -> 部署合約 -> 各 TPS 送 attestAndSettle 量確認延遲/TPS -> 收尾。
"""
import os
import sys
import time
import json
import signal
import subprocess
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
JAVA_HOME = r"C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot"
JAVA = str(Path(JAVA_HOME) / "bin" / "java.exe")
BESU_HOME = ROOT / "besu-dist25" / "besu-25.4.1"
JVM_OPTS = [
    "-Dvertx.disableFileCPResolving=true", f"-Dbesu.home={BESU_HOME}",
    "-Dlog4j.shutdownHookEnabled=false", "-Dlog4j2.formatMsgNoLookups=true",
    "-Djava.util.logging.manager=org.apache.logging.log4j.jul.LogManager",
    "--add-opens", "java.base/sun.security.provider=ALL-UNNAMED",
    "--add-opens", "java.base/java.util=ALL-UNNAMED",
    "-Dio.netty.tryReflectionSetAccessible=true",
    "--add-exports", "java.base/jdk.internal.misc=ALL-UNNAMED",
    "--add-opens", "java.base/java.nio=ALL-UNNAMED", "-Xmx900m",
]
CLASSPATH = str(BESU_HOME / "lib" / "*")
NETDIR = os.environ.get("FOGHAIL_NETDIR", "networkFiles")   # networkFiles 或 networkFiles1s
SUF = os.environ.get("FOGHAIL_SUF", "")                      # 資料夾/結果檔後綴
GENESIS = str(ROOT / NETDIR / "genesis.json")
KEYS = ROOT / NETDIR / "keys"
LOGDIR = ROOT / "out" / f"nodelogs{SUF}"; LOGDIR.mkdir(parents=True, exist_ok=True)

RPC = "http://127.0.0.1:8545"
BASE_P2P, BASE_RPC = 30303, 8545


def node_dirs():
    return sorted([d for d in KEYS.iterdir() if d.is_dir()])


def enode_of(keydir, port):
    pub = open(keydir / "key.pub").read().strip()
    if pub.startswith("0x"):
        pub = pub[2:]
    return f"enode://{pub}@127.0.0.1:{port}"


def start_nodes():
    dirs = node_dirs()
    assert len(dirs) == 4, f"需要 4 個節點金鑰，實得 {len(dirs)}"
    boot = enode_of(dirs[0], BASE_P2P)
    env = dict(os.environ, JAVA_HOME=JAVA_HOME)
    procs = []
    for i, d in enumerate(dirs):
        p2p = BASE_P2P + i; rpc = BASE_RPC + i
        data = ROOT / "out" / f"node{i+1}{SUF}"; data.mkdir(parents=True, exist_ok=True)
        besu_args = [f"--data-path={data}", f"--genesis-file={GENESIS}",
                f"--node-private-key-file={d/'key'}", f"--p2p-port={p2p}",
                "--rpc-http-enabled", "--rpc-http-api=ETH,NET,WEB3,QBFT,TXPOOL",
                f"--rpc-http-port={rpc}", "--rpc-http-host=127.0.0.1",
                "--host-allowlist=*", "--min-gas-price=0"]
        if i != 0:
            besu_args.append(f"--bootnodes={boot}")
        cmd = [JAVA] + JVM_OPTS + ["-cp", CLASSPATH, "org.hyperledger.besu.Besu"] + besu_args
        log = open(LOGDIR / f"node{i+1}.log", "w", encoding="utf-8", errors="replace")
        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                             env=env, cwd=str(ROOT))
        procs.append(p)
        # 核心綁定：每節點專屬 2 核（模擬「各自主機」，消除 CPU 競爭，讓 1s 出塊穩定）
        aff = os.environ.get("FOGHAIL_AFFINITY")
        if aff:
            try:
                import psutil
                cores = [2 * i, 2 * i + 1]
                psutil.Process(p.pid).cpu_affinity(cores)
                print(f"  起 node{i+1}: p2p={p2p} rpc={rpc} pid={p.pid} 綁核心={cores}")
            except Exception as e:
                print(f"  起 node{i+1}: pid={p.pid}（綁核心失敗 {e}）")
        else:
            print(f"  起 node{i+1}: p2p={p2p} rpc={rpc} pid={p.pid}")
    return procs


def wait_for_blocks(timeout=180):
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(RPC))
    t0 = time.time()
    last = -1
    while time.time() - t0 < timeout:
        try:
            if w3.is_connected():
                bn = w3.eth.block_number
                if bn != last:
                    print(f"  區塊高度 = {bn}")
                    last = bn
                if bn >= 2:
                    return w3
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("等不到出塊")


def deploy(w3):
    from web3 import Web3
    key = open(ROOT / "out" / "deployer.key").read().strip()
    acct = w3.eth.account.from_key(key)
    abi = json.load(open(ROOT / "out" / "FogHailAttestation.abi.json"))
    binv = open(ROOT / "out" / "FogHailAttestation.bin").read().strip()
    C = w3.eth.contract(abi=abi, bytecode=binv)
    nonce = w3.eth.get_transaction_count(acct.address)
    tx = C.constructor().build_transaction({"from": acct.address, "nonce": nonce,
        "gas": 1_500_000, "gasPrice": 0, "chainId": w3.eth.chain_id})
    signed = acct.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(signed.raw_transaction)
    rcpt = w3.eth.wait_for_transaction_receipt(h, timeout=60)
    print(f"  合約部署於 {rcpt.contractAddress}（gas={rcpt.gasUsed}）")
    return acct, rcpt.contractAddress, abi


def bench(w3, others, acct, addr, abi, tps, n):
    """others: 其他節點的 Web3（廣播已簽交易，模擬真實網路的交易池傳播，
    量到的才是 QBFT 共識確認延遲，而非單節點提交的提案輪轉假影）。"""
    import secrets, statistics
    c = w3.eth.contract(address=addr, abi=abi)
    lat, sizes, gas = [], [], []
    interval = 1.0 / tps
    nonce = w3.eth.get_transaction_count(acct.address)
    for i in range(n):
        loop = time.perf_counter()
        trip = secrets.token_bytes(32); rp = secrets.token_bytes(32); dp = secrets.token_bytes(32)
        tx = c.functions.attestAndSettle(trip, rp, dp, 1, 1).build_transaction({
            "from": acct.address, "nonce": nonce, "gas": 250000, "gasPrice": 0,
            "chainId": w3.eth.chain_id})
        signed = acct.sign_transaction(tx)
        t0 = time.perf_counter()
        h = w3.eth.send_raw_transaction(signed.raw_transaction)
        for o in others:            # 廣播到其他節點的交易池
            try:
                o.eth.send_raw_transaction(signed.raw_transaction)
            except Exception:
                pass                # already known 之類忽略
        rcpt = w3.eth.wait_for_transaction_receipt(h, timeout=30)
        lat.append(time.perf_counter() - t0)
        sizes.append(len(signed.raw_transaction)); gas.append(rcpt.gasUsed)
        nonce += 1
        dt = time.perf_counter() - loop
        if dt < interval:
            time.sleep(interval - dt)
    lat.sort()
    q = lambda p: lat[min(len(lat) - 1, int(p * len(lat)))]
    return {"tps": tps, "n": n, "conf_p50_s": round(q(.5), 3), "conf_p95_s": round(q(.95), 3),
            "tx_bytes": int(statistics.median(sizes)), "gas": int(statistics.median(gas))}


def main():
    procs = start_nodes()
    results = {}
    try:
        w3 = wait_for_blocks()
        print(f"  已連線，chainId={w3.eth.chain_id}")
        acct, addr, abi = deploy(w3)
        from web3 import Web3
        others = [Web3(Web3.HTTPProvider(f"http://127.0.0.1:{BASE_RPC + i}")) for i in (1, 2, 3)]
        rows = []
        for tps in (10, 50, 100):
            r = bench(w3, others, acct, addr, abi, tps, n=40)
            print(f"  TPS={tps}: 確認 p50={r['conf_p50_s']}s p95={r['conf_p95_s']}s "
                  f"tx={r['tx_bytes']}B gas={r['gas']}")
            rows.append(r)
        results = {"contract": addr, "rows": rows}
        json.dump(results, open(ROOT / "out" / f"e6_results{SUF}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(f"\n-> {ROOT/'out'/'e6_results.json'}")
    finally:
        print("收尾：關閉節點 …")
        for p in procs:
            # /T 連同子 java 行程一起關；只殺我們起的 PID 樹，不動其他 java
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                           capture_output=True)
        time.sleep(2)
    return results


if __name__ == "__main__":
    main()
