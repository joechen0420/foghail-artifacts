# -*- coding: utf-8 -*-
"""產出 §6.1 資料統計表。輸出 data/ground_truth/stats_summary.txt。"""
import sys
import numpy as np
import pandas as pd
import config as C

sys.stdout.reconfigure(encoding="utf-8")


def main():
    reqs = pd.read_parquet(C.CLEAN / "trips_grid.parquet")
    sup = pd.read_parquet(C.CLEAN / "driver_supply.parquet")
    orc = pd.read_parquet(C.GT / "oracle_topk.parquet")

    lines = []
    def p(s=""):
        lines.append(s); print(s)

    p("=== FogHail Phase 0 資料統計（§6.1） ===")
    p(f"請求數（上車事件）：{len(reqs):,}")
    p(f"供給數（下車事件，ρ={C.RHO}）：{len(sup):,}")

    # 每 30s 窗請求數分布
    t0 = reqs["pu_ts"].min()
    win = ((reqs["pu_ts"] - t0).dt.total_seconds() // C.BATCH_WINDOW_S).astype(int)
    per_win = win.value_counts().sort_index()
    p(f"每 {C.BATCH_WINDOW_S}s 窗請求數 p50/p95：{per_win.median():.0f} / {per_win.quantile(.95):.0f}")

    # 可用駕駛池
    p(f"可用駕駛池大小 p50/p95：{orc['pool_size'].median():.0f} / {orc['pool_size'].quantile(.95):.0f}")

    # 媒合可行率
    for r in C.RADII_M:
        frac = (orc[f"n_within_{r}m"] > 0).mean()
        p(f"{r}m 內有 ≥1 可用駕駛的請求比例：{frac:.1%}")

    # 最近駕駛距離
    p(f"最近駕駛距離 p50/p95：{orc['nn_dist_k1'].median():.0f} / {orc['nn_dist_k1'].quantile(.95):.0f} m")

    # 空間密度：每 cell 請求數（各 grid）
    for g in C.GRID_SIZES:
        cell = reqs.groupby([f"pu_gx_{g}", f"pu_gy_{g}"]).size()
        p(f"grid={g}m：占用 cell 數 {len(cell):,}，每 cell 請求 p50/p95 {cell.median():.0f}/{cell.quantile(.95):.0f}，最熱 cell {cell.max()}")

    dst = C.GT / "stats_summary.txt"
    dst.write_text("\n".join(lines), encoding="utf-8")
    p(f"\n已存 -> {dst}")


if __name__ == "__main__":
    main()
