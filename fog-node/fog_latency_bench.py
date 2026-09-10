# -*- coding: utf-8 -*-
"""FogHail 霧端媒合延遲量測 —— 在這台機器上重現論文的「0.28 ms」那格。

量的是：一個乘客請求（9 格布隆過濾器）對一個駕駛池做盲測成員判定所花的時間。
與論文 experiments/phase2/oride_ref.py 的 foghail_fog_latency() 邏輯完全一致，
但改用標準庫，零外部依賴，任何有 Python 3 的機器都能直接跑。

用法：
    python fog_latency_bench.py

對齊 t3.medium 的 2 vCPU（Linux/Pi，選配）：
    taskset -c 0-1 python fog_latency_bench.py
"""
import time
import random
import statistics
import platform
from bloom import BF

M = 512          # 布隆過濾器位元長度（與論文一致）
K = 5            # 雜湊函數個數（與論文一致）
SALT = "epoch-0001"   # 任意固定鹽值；值不影響延遲
REPEAT = 7       # 每個池大小重複次數，取中位數
GRID_SPAN = 500  # 隨機格子的範圍（模擬服務區）


def bench(pool, seed=42):
    """量『1 個乘客請求 vs pool 台駕駛』的盲測媒合時間（毫秒）。"""
    rng = random.Random(seed)
    bf = BF(M, K, SALT)
    # 乘客：上車格 + 8 鄰域共 9 格 → BF_p
    rc = (rng.randrange(GRID_SPAN), rng.randrange(GRID_SPAN))
    bf_p = bf.build([(rc[0] + dx, rc[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
    # 駕駛池：每台只編自己 1 格
    drv = [bf.cell_bits((rng.randrange(GRID_SPAN), rng.randrange(GRID_SPAN)))
           for _ in range(pool)]
    # 計時：對每台駕駛做精確成員判定 (BF_d AND BF_p) == BF_d
    t = time.perf_counter()
    for dm in drv:
        _ = (dm & bf_p) == dm
    return (time.perf_counter() - t) * 1000.0


def main():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("=" * 60)
    print("FogHail 霧端媒合延遲量測")
    print("機器：", platform.processor() or platform.machine(),
          "| 核心數：", _cpu_count(), "| Python", platform.python_version())
    print(f"參數：m={M}, k={K}（與論文一致）；每個池大小取 {REPEAT} 次中位數")
    print("-" * 60)
    for pool in (100, 1000, 10000):
        ms = sorted(bench(pool, seed=s) for s in range(REPEAT))
        med = statistics.median(ms)
        print(f"  駕駛池 = {pool:>6}：{med:8.3f} ms   （{med / pool * 1000:6.2f} us/駕駛）")
    print("-" * 60)
    print(f"通訊量：每請求上傳 1 個布隆過濾器 = {M // 8} bytes；互動輪數 = 1（非互動）")
    print("論文對照（表 2）：本系統 (BF) 霧端媒合 0.28 ms（池=1000）、64 B、1 輪")
    print("=" * 60)
    print("※ 請記下『池=1000』那行的 ms，以及上面的機器型號/核心數/RAM，寫進論文 §5。")


def _cpu_count():
    try:
        import os
        return os.cpu_count()
    except Exception:
        return "?"


if __name__ == "__main__":
    main()
