# -*- coding: utf-8 -*-
"""E4/E7 隱私攻擊實驗（Phase 6），填論文表 4（§6.4）。

E4a 字典攻擊：攻擊者知編碼規則。分兩種——(i) 知當期 salt：對加鹽 BF 反推 cell；
     (ii) 用過期 salt（已輪換）：驗證 salt 輪換使預計算字典失效。
E4b 位置蒐割：惡意乘客只得 match/no-match，二分搜尋定位一位駕駛所需查詢數，
     對照 ORide 單次查詢即洩漏（Kumaraswamy 45%）。
E7  假名連結 AUC：BF 位元重疊為分數，比較同 salt（同 epoch）vs 跨 salt（跨 epoch），
     量化 salt 輪換提供的跨期不可連結性。
"""
import sys
import math
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"; OUT.mkdir(exist_ok=True)

# phase0 config + phase1 bloom
def _load(name, rel):
    p = Path(__file__).resolve().parent.parent / rel
    s = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
C0 = _load("p0", "phase0/config.py")
BLOOM = _load("bloom", "phase1/bloom.py")
BF = BLOOM.BF

M, K, GRID = 512, 5, C0.DEFAULT_GRID
SALT0, SALT1 = "foghail-epoch-0", "foghail-epoch-1"
rng = np.random.default_rng(42)


def occupied_cells():
    """服務區域內出現過的 cell（攻擊者字典 = 這些候選 cell）。"""
    sup = pd.read_parquet(C0.CLEAN / "driver_supply.parquet")
    cells = list(set(zip(sup[f"gx_{GRID}"].tolist(), sup[f"gy_{GRID}"].tolist())))
    return cells


def neigh(gx, gy):
    return [(gx + dx, gy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]


# ---------- E4a 字典攻擊 ----------
def e4a_dictionary(cells, n_targets=1000):
    bf = BF(M, K, SALT0)
    # 建當期字典：cell -> 位元遮罩
    dict_bits = {c: bf.cell_bits(c) for c in cells}
    inv = {}
    for c, b in dict_bits.items():
        inv.setdefault(b, []).append(c)
    targets = [cells[i] for i in rng.choice(len(cells), min(n_targets, len(cells)), replace=False)]

    # (i) 知 salt：駕駛 1-cell BF_d 反推
    drv_hit = 0
    for c in targets:
        bd = bf.cell_bits(c)
        cand = inv.get(bd, [])
        if c in cand:
            drv_hit += 1
    drv_top1 = drv_hit / len(targets)

    # 乘客 9-cell BF_p：反推鄰域成員（能不能框到上車鄰域）
    rider_nbhd_hit = 0
    for c in targets:
        bfp = bf.build(neigh(*c))
        # 找出所有 bits ⊆ BF_p 的 cell（成員）
        members = [cc for cc, bb in dict_bits.items() if (bb & bfp) == bb]
        if c in members:          # 上車 cell 落在還原鄰域內
            rider_nbhd_hit += 1
    rider_nbhd = rider_nbhd_hit / len(targets)

    # (ii) 過期 salt：攻擊者拿 SALT1 的字典去反推 SALT0 的 BF
    bf_stale = BF(M, K, SALT1)
    stale_dict = {}
    for c in cells:
        stale_dict.setdefault(bf_stale.cell_bits(c), []).append(c)
    stale_hit = 0
    for c in targets:
        bd = bf.cell_bits(c)      # 目標用當期 salt
        cand = stale_dict.get(bd, [])
        if c in cand:
            stale_hit += 1
    stale_top1 = stale_hit / len(targets)

    return {"driver_cell_top1_saltknown": drv_top1,
            "rider_neighborhood_recover": rider_nbhd,
            "driver_cell_top1_stalesalt": stale_top1,
            "neighborhood_area_km2": round(9 * (GRID / 1000) ** 2, 3)}


# ---------- E4b 位置蒐割（二分搜尋查詢數）----------
def e4b_harvesting(cells, n_drivers=500):
    """惡意乘客只得 match/no-match（成員 oracle）。二分搜尋定位一位駕駛的 cell。
    對照 ORide：單次查詢即洩漏位置。"""
    N = len(cells)
    idx = {c: i for i, c in enumerate(cells)}
    queries = []
    for _ in range(n_drivers):
        target = cells[int(rng.integers(N))]
        lo, hi = 0, N            # 在 cell 索引空間二分（攻擊者可自訂 BF_p 覆蓋任意集合）
        # 用「目標索引」模擬成員 oracle：每次問「目標 ∈ 前半?」
        q = 0
        cand = list(range(N))
        rng.shuffle(cand)
        t = cand.index(idx[target])
        loi, hii = 0, len(cand)
        while hii - loi > 1:
            mid = (loi + hii) // 2
            q += 1               # 一次查詢 = 一個 match/no-match
            if t < mid:
                hii = mid
            else:
                loi = mid
        queries.append(q)
    queries = np.array(queries)
    return {"service_cells_N": N,
            "median_queries_to_localize": int(np.median(queries)),
            "p95_queries": int(np.percentile(queries, 95)),
            "theoretical_log2N": round(math.log2(N), 1),
            "oride_queries": 1}


# ---------- E7 假名連結 AUC ----------
def e7_linkage(cells, n_pairs=4000):
    """BF 位元重疊為連結分數。正對=同 cell、負對=不同 cell。
    比較同 salt（同 epoch，可連結）vs 跨 salt（跨 epoch，應不可連結 AUC~0.5）。"""
    def bit_overlap(a, b):
        return (a & b).bit_count()

    def auc_for(same_salt):
        bf_a = BF(M, K, SALT0)
        bf_b = BF(M, K, SALT0 if same_salt else SALT1)
        scores, labels = [], []
        for _ in range(n_pairs):
            c = cells[int(rng.integers(len(cells)))]
            # 正對：同一 cell（同一使用者不同上傳/輪換後）
            scores.append(bit_overlap(bf_a.cell_bits(c), bf_b.cell_bits(c))); labels.append(1)
            # 負對：不同 cell（不同使用者）
            c2 = cells[int(rng.integers(len(cells)))]
            while c2 == c:
                c2 = cells[int(rng.integers(len(cells)))]
            scores.append(bit_overlap(bf_a.cell_bits(c), bf_b.cell_bits(c2))); labels.append(0)
        return roc_auc_score(labels, scores)

    return {"auc_same_epoch": round(auc_for(True), 3),
            "auc_cross_epoch": round(auc_for(False), 3)}


def main():
    import json
    cells = occupied_cells()
    print(f"服務區域候選 cell 數 N = {len(cells)}（grid={GRID}m）\n")

    print("E4a 字典攻擊 …")
    a = e4a_dictionary(cells)
    print(f"  知 salt：駕駛 cell top-1 還原 = {a['driver_cell_top1_saltknown']:.1%}")
    print(f"  知 salt：乘客上車鄰域還原 = {a['rider_neighborhood_recover']:.1%}"
          f"（洩漏界＝9 格 {a['neighborhood_area_km2']} km²）")
    print(f"  過期 salt：駕駛 cell 還原 = {a['driver_cell_top1_stalesalt']:.1%}（salt 輪換使字典失效）")

    print("\nE4b 位置蒐割 …")
    b = e4b_harvesting(cells)
    print(f"  定位一位駕駛所需查詢數 中位數 = {b['median_queries_to_localize']}"
          f"（p95={b['p95_queries']}，理論 log2(N)={b['theoretical_log2N']}）")
    print(f"  對照 ORide：{b['oride_queries']} 次查詢即洩漏位置")

    print("\nE7 假名連結 AUC …")
    e = e7_linkage(cells)
    print(f"  同 epoch（同 salt）AUC = {e['auc_same_epoch']}（可連結）")
    print(f"  跨 epoch（salt 輪換）AUC = {e['auc_cross_epoch']}（≈0.5=不可連結）")

    out = {"N_cells": len(cells), "e4a_dictionary": a, "e4b_harvesting": b, "e7_linkage": e}
    json.dump(out, open(OUT / "phase6_attacks.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n-> {OUT/'phase6_attacks.json'}")


if __name__ == "__main__":
    main()
