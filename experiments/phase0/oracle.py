# -*- coding: utf-8 -*-
"""明文 Oracle：每筆請求的 top-k 最近可用駕駛與半徑內駕駛數（ground truth）。

作法：以 BATCH_WINDOW_S 分窗；每窗的可用駕駛池 = 下車時間落在
[窗起 − DRIVER_AVAIL_WINDOW_S, 窗迄] 的供給事件。每窗建 KDTree 查詢。
距離為投影公尺平面上的歐氏距離。

輸入：trips_grid.parquet（請求=上車事件）、driver_supply.parquet
輸出：data/ground_truth/oracle_topk.parquet
"""
import sys
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
import config as C

sys.stdout.reconfigure(encoding="utf-8")


def run_oracle(reqs, sup):
    reqs = reqs.sort_values("pu_ts").reset_index(drop=True)
    sup = sup.sort_values("time").reset_index(drop=True)
    sup_t = sup["time"].values.astype("datetime64[s]").astype(np.int64)
    sup_xy = sup[["x", "y"]].values

    t0 = reqs["pu_ts"].min().to_datetime64().astype("datetime64[s]").astype(np.int64)
    req_t = reqs["pu_ts"].values.astype("datetime64[s]").astype(np.int64)
    win_id = (req_t - t0) // C.BATCH_WINDOW_S

    maxk = max(C.TOPK)
    recs = []
    for w, idx in pd.Series(range(len(reqs))).groupby(win_id):
        idx = idx.values
        w_start = t0 + int(w) * C.BATCH_WINDOW_S
        w_end = w_start + C.BATCH_WINDOW_S
        lo = w_start - C.DRIVER_AVAIL_WINDOW_S
        mask = (sup_t >= lo) & (sup_t <= w_end)
        pool = sup_xy[mask]
        if len(pool) == 0:
            for i in idx:
                recs.append((i, 0, *[np.nan] * len(C.TOPK), *[0] * len(C.RADII_M)))
            continue
        tree = cKDTree(pool)
        q = reqs.loc[idx, ["pu_x", "pu_y"]].values
        kq = min(maxk, len(pool))
        dist, _ = tree.query(q, k=kq)
        dist = dist.reshape(len(idx), kq)   # k=1 時 query 會壓成 1D，補回二維
        for row, i in enumerate(idx):
            dvec = dist[row]
            topk_d = [float(dvec[k - 1]) if k <= kq else np.nan for k in C.TOPK]
            # 半徑內數量須查整個 pool（不只 top-maxk）
            full = tree.query_ball_point(q[row], max(C.RADII_M))
            fd = np.linalg.norm(pool[full] - q[row], axis=1) if full else np.array([])
            rad_counts = [int((fd <= r).sum()) for r in C.RADII_M]
            recs.append((i, len(pool), *topk_d, *rad_counts))

    cols = (["req_idx", "pool_size"]
            + [f"nn_dist_k{k}" for k in C.TOPK]
            + [f"n_within_{r}m" for r in C.RADII_M])
    out = pd.DataFrame(recs, columns=cols).sort_values("req_idx").reset_index(drop=True)
    return out


def main():
    reqs = pd.read_parquet(C.CLEAN / "trips_grid.parquet")
    sup = pd.read_parquet(C.CLEAN / "driver_supply.parquet")
    print(f"請求 {len(reqs)} 筆、供給 {len(sup)} 筆，跑 Oracle …")
    out = run_oracle(reqs, sup)
    dst = C.GT / "oracle_topk.parquet"
    out.to_parquet(dst, index=False)
    matched = (out["n_within_500m"] > 0).mean()
    print(f"完成 -> {dst}")
    print(f"  500m 內有可用駕駛的請求比例：{matched:.1%}")
    print(f"  最近駕駛距離中位數：{out['nn_dist_k1'].median():.0f} m")


if __name__ == "__main__":
    main()
