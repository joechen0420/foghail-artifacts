# -*- coding: utf-8 -*-
"""BRIP 嵌入媒合品質。與 Phase 1 相同的窗/池/Oracle，唯媒合規則改為：
DApp（明文）以 COR2Vec 嵌入的 cosine 相似度選最高分駕駛（argmax）。
"""
import sys
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
import config as C
from embed_lookup import Cor2Vec

sys.stdout.reconfigure(encoding="utf-8")


def run_brip(max_requests=C.MAX_REQUESTS, seed=C.RANDOM_SEED):
    cv = Cor2Vec()
    reqs = pd.read_parquet(C.CLEAN / "trips_grid.parquet")
    sup = pd.read_parquet(C.CLEAN / "driver_supply.parquet")
    if max_requests and len(reqs) > max_requests:
        reqs = reqs.sample(max_requests, random_state=seed)
    reqs = reqs.sort_values("pu_ts").reset_index(drop=True)
    sup = sup.sort_values("time").reset_index(drop=True)

    sup_t = sup["time"].values.astype("datetime64[s]").astype(np.int64)
    sup_xy = sup[["x", "y"]].values
    # 預先算每個供給點的嵌入索引
    sup_emb_i = np.array([cv.idx_of_xy(x, y) for x, y in sup_xy])

    t0 = reqs["pu_ts"].min().to_datetime64().astype("datetime64[s]").astype(np.int64)
    req_t = reqs["pu_ts"].values.astype("datetime64[s]").astype(np.int64)
    win_id = (req_t - t0) // C.BATCH_WINDOW_S
    maxk = max(C.TOPK)

    hits = {kk: 0 for kk in C.TOPK}
    infl, absd, matched_n, nonempty_n = [], [], 0, 0

    for w, idx in pd.Series(range(len(reqs))).groupby(win_id):
        idx = idx.values
        w_start = t0 + int(w) * C.BATCH_WINDOW_S
        w_end = w_start + C.BATCH_WINDOW_S
        lo = w_start - C.DRIVER_AVAIL_WINDOW_S
        pmask = (sup_t >= lo) & (sup_t <= w_end)
        pidx = np.nonzero(pmask)[0]
        if len(pidx) == 0:
            continue
        pool_xy = sup_xy[pidx]
        pool_emb = cv.emb[sup_emb_i[pidx]]          # (P, d)
        tree = cKDTree(pool_xy)

        for i in idx:
            nonempty_n += 1
            rq = np.array([reqs.at[i, "pu_x"], reqs.at[i, "pu_y"]])
            rvec = cv.vec_xy(rq[0], rq[1])
            sims = pool_emb @ rvec                   # cosine（皆已正規化）
            win_j = int(np.argmax(sims))            # 最高相似度 = 推薦駕駛
            matched_n += 1
            dwin = float(np.linalg.norm(pool_xy[win_j] - rq))
            kq = min(maxk, len(pidx))
            dists, _ = tree.query(rq, k=kq)
            dists = np.atleast_1d(dists)
            nearest = float(dists[0])
            for kk in C.TOPK:
                if dwin <= dists[min(kk, kq) - 1] + 1e-6:
                    hits[kk] += 1
            absd.append(dwin)
            if nearest > 1e-6:
                infl.append(dwin / nearest)

    infl = np.array(infl); absd = np.array(absd)
    return {
        "method": "BRIP(embedding)", "requests": nonempty_n,
        "hit@1": hits[1] / max(matched_n, 1),
        "hit@3": hits[3] / max(matched_n, 1),
        "hit@5": hits[5] / max(matched_n, 1),
        "infl_p50": float(np.median(infl)), "infl_p95": float(np.percentile(infl, 95)),
        "pickup_m_p50": float(np.median(absd)), "pickup_m_p95": float(np.percentile(absd, 95)),
    }


if __name__ == "__main__":
    r = run_brip()
    print("=== BRIP 嵌入媒合 ===")
    for k, v in r.items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")
