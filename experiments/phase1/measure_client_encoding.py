# -*- coding: utf-8 -*-
"""E3 用戶端編碼延遲（參考平台量測）：T = T_grid + T_neighbor + T_bloom + T_sign。

在本機 CPU 量測（非手機）。手機值需 Kotlin 實機（見 Kotlin_App_Build指南）；
此為「參考平台」數字，供論文先有真實量級，並顯示編碼極輕量。
"""
import sys
import time
import importlib.util
from pathlib import Path
import numpy as np
from ecdsa import NIST256p, SigningKey
from bloom import BF

sys.stdout.reconfigure(encoding="utf-8")

# phase0 config（投影/網格）
_p0 = Path(__file__).resolve().parent.parent / "phase0" / "config.py"
_spec = importlib.util.spec_from_file_location("p0", _p0)
C0 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(C0)

GRID = C0.DEFAULT_GRID
M, K, SALT = 512, 5, "foghail-epoch-0"
WARMUP, ITERS = 200, 2000


def neighborhood(gx, gy):
    return [(gx + dx, gy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]


def measure(lat=40.75, lon=-73.99):
    bf = BF(M, K, SALT)
    sk = SigningKey.generate(curve=NIST256p)
    tg, tn, tb, ts = [], [], [], []
    for it in range(WARMUP + ITERS):
        t0 = time.perf_counter()
        x, y = C0.to_meters(np.array([lat]), np.array([lon]))
        gx = int(np.floor(x[0] / GRID)); gy = int(np.floor(y[0] / GRID))
        t1 = time.perf_counter()
        nb = neighborhood(gx, gy)
        t2 = time.perf_counter()
        bfp = bf.build(nb)
        payload = bfp.to_bytes((M + 7) // 8, "little")
        t3 = time.perf_counter()
        sk.sign(payload)
        t4 = time.perf_counter()
        if it >= WARMUP:
            ms = 1000.0
            tg.append((t1 - t0) * ms); tn.append((t2 - t1) * ms)
            tb.append((t3 - t2) * ms); ts.append((t4 - t3) * ms)
    def stat(a):
        a = np.array(a)
        return float(np.median(a)), float(np.percentile(a, 95))
    segs = {"T_grid": stat(tg), "T_neighbor": stat(tn),
            "T_bloom": stat(tb), "T_sign": stat(ts)}
    total = np.array(tg) + np.array(tn) + np.array(tb) + np.array(ts)
    segs["T_total"] = (float(np.median(total)), float(np.percentile(total, 95)))
    return segs


def main():
    import json
    r = measure()
    print("E3 用戶端編碼延遲（本機 CPU 參考平台，非手機）")
    print(f"{'段落':<12}{'p50(ms)':>10}{'p95(ms)':>10}")
    for k, (p50, p95) in r.items():
        print(f"{k:<12}{p50:>10.4f}{p95:>10.4f}")
    out = {k: {"p50_ms": v[0], "p95_ms": v[1]} for k, v in r.items()}
    (Path(__file__).resolve().parent / "out").mkdir(exist_ok=True)
    json.dump(out, open(Path(__file__).resolve().parent / "out" / "e3_client_ref.json",
              "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n註：桌機 CPU 遠快於手機；手機值需 Kotlin 實機量測（見 Kotlin_App_Build指南）。")
    print("對照 ORide 手機端 15–26 ms、PrivateRide AC 554 ms（LG G3）。")


if __name__ == "__main__":
    main()
