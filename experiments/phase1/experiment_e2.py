# -*- coding: utf-8 -*-
"""E2：BF 盲媒合品質。對照 Phase 0 明文 Oracle 計算 Hit@k、接駕膨脹比、
BF 偽陰/偽陽率、媒合可行率。

作法：30 秒批次窗；每窗建可用駕駛池（KDTree 供 Oracle 最近距離、
cell 空間雜湊供成員查詢）。乘客編碼 9 格 BF_p、駕駛編碼 1 格 BF_d，
霧節點 C_int≥k 判定；多位 match 依策略選勝出者，再與 Oracle 比對。
"""
import sys
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
import config as C
from bloom import BF

sys.stdout.reconfigure(encoding="utf-8")


def _neighbors(gx, gy):
    return [(gx + dx, gy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]


def run_e2(grid=C.DEFAULT_GRID, m=C.M_DEFAULT, k=C.K_DEFAULT,
           strategy="weighted_random", max_requests=C.MAX_REQUESTS,
           seed=C.RANDOM_SEED, insitu_fp_windows=40, decision="membership"):
    """decision: 'membership' = (BF_d AND BF_p)==BF_d（正確，無偽陰）；
                 'threshold'  = C_int>=k（論文原式，會有內部碰撞偽陰）。"""
    rng = np.random.default_rng(seed)
    bf = BF(m, k, C.SALT)

    reqs = pd.read_parquet(C.CLEAN / "trips_grid.parquet")
    sup = pd.read_parquet(C.CLEAN / "driver_supply.parquet")
    if max_requests and len(reqs) > max_requests:
        reqs = reqs.sample(max_requests, random_state=seed)
    reqs = reqs.sort_values("pu_ts").reset_index(drop=True)
    sup = sup.sort_values("time").reset_index(drop=True)

    gxcol, gycol = f"pu_gx_{grid}", f"pu_gy_{grid}"
    sgx, sgy = f"gx_{grid}", f"gy_{grid}"
    sup_t = sup["time"].values.astype("datetime64[s]").astype(np.int64)
    sup_xy = sup[["x", "y"]].values
    sup_cell = list(zip(sup[sgx].values.tolist(), sup[sgy].values.tolist()))

    t0 = reqs["pu_ts"].min().to_datetime64().astype("datetime64[s]").astype(np.int64)
    req_t = reqs["pu_ts"].values.astype("datetime64[s]").astype(np.int64)
    win_id = (req_t - t0) // C.BATCH_WINDOW_S
    maxk = max(C.TOPK)

    hits = {kk: 0 for kk in C.TOPK}
    infl, absd, matched_n, nonempty_n = [], [], 0, 0
    fn = fp = fp_tests = fn_tests = 0
    win_seen = 0

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
        tree = cKDTree(pool_xy)
        # cell -> pool 內索引
        by_cell = {}
        for j, gi in enumerate(pidx):
            by_cell.setdefault(sup_cell[gi], []).append(j)

        win_seen += 1
        do_insitu_fp = win_seen <= insitu_fp_windows

        for i in idx:
            nonempty_n += 1
            rc = (int(reqs.at[i, gxcol]), int(reqs.at[i, gycol]))
            rq = np.array([reqs.at[i, "pu_x"], reqs.at[i, "pu_y"]])
            neigh = _neighbors(*rc)
            bf_p = bf.build(neigh)

            # 成員（駕駛 cell 落在 9 格內）
            members = []
            for nc in neigh:
                members.extend(by_cell.get(nc, []))
            # BF 驗證成員（量 FNR）
            matched = []
            for j in members:
                dmask = bf.cell_bits(sup_cell[pidx[j]])
                mask_arg = dmask if decision == "membership" else None
                ok, _ = bf.is_match(dmask, bf_p, driver_mask=mask_arg)
                fn_tests += 1
                if ok:
                    matched.append(j)
                else:
                    fn += 1
            # in-situ 偽陽（抽樣非成員）
            if do_insitu_fp:
                memset = set(members)
                nonmem = [j for j in range(len(pidx)) if j not in memset]
                if nonmem:
                    samp = rng.choice(nonmem, size=min(30, len(nonmem)), replace=False)
                    for j in samp:
                        dmask = bf.cell_bits(sup_cell[pidx[j]])
                        mask_arg = dmask if decision == "membership" else None
                        ok, _ = bf.is_match(dmask, bf_p, driver_mask=mask_arg)
                        fp_tests += 1
                        fp += int(ok)

            if not matched:
                continue
            matched_n += 1
            # 勝出策略（霧節點無距離資訊）
            if strategy == "first_come":
                win_j = min(matched, key=lambda j: sup_t[pidx[j]])
            elif strategy == "max_bits":
                win_j = max(matched, key=lambda j: bf.intersect_count(
                    bf.cell_bits(sup_cell[pidx[j]]), bf_p))
            else:  # weighted_random
                win_j = int(rng.choice(matched))

            dwin = float(np.linalg.norm(pool_xy[win_j] - rq))
            kq = min(maxk, len(pidx))
            dists, _ = tree.query(rq, k=kq)
            dists = np.atleast_1d(dists)
            nearest = float(dists[0])
            for kk in C.TOPK:
                kth = dists[min(kk, kq) - 1]
                if dwin <= kth + 1e-6:
                    hits[kk] += 1
            absd.append(dwin)
            if nearest > 1e-6:
                infl.append(dwin / nearest)

    infl = np.array(infl) if infl else np.array([np.nan])
    absd = np.array(absd) if absd else np.array([np.nan])
    res = {
        "grid": grid, "m": m, "k": k, "strategy": strategy,
        "requests": nonempty_n,
        "match_rate": matched_n / max(nonempty_n, 1),
        "hit@1": hits[1] / max(matched_n, 1),
        "hit@3": hits[3] / max(matched_n, 1),
        "hit@5": hits[5] / max(matched_n, 1),
        "infl_p50": float(np.nanmedian(infl)),
        "infl_p95": float(np.nanpercentile(infl, 95)),
        "pickup_m_p50": float(np.nanmedian(absd)),
        "pickup_m_p95": float(np.nanpercentile(absd, 95)),
        "bf_fnr": fn / max(fn_tests, 1),
        "bf_fpr_insitu": fp / max(fp_tests, 1),
        "fp_tests": fp_tests,
    }
    return res


if __name__ == "__main__":
    r = run_e2()
    print("=== E2 預設參數 (grid=250, m=512, k=5, weighted_random) ===")
    for kk, v in r.items():
        print(f"  {kk}: {v:.4f}" if isinstance(v, float) else f"  {kk}: {v}")
