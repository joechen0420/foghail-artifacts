# -*- coding: utf-8 -*-
"""E7b 匿名集合：知道每期 salt 的攻擊者，把每次上傳解回 cell 之後，還剩多少不確定性。

背景（同事外審第 1 題，2026-10-14）：E7 的 AUC 0.495 只量「比對位元圖樣、不重新解碼」的攻擊者。
salt 公開時，攻擊者可逐期用字典攻擊把 BF 解回 cell（Table 6：駕駛 cell 100%、乘客 9 格鄰域 100%），
此時跨期保護只剩兩件事：假名輪換，以及同一 epoch、同一 cell 裡有多少其他使用者（匿名集合 k）。

定義：
- 乘客：每趟一個假名、一次上傳；9 格鄰域解碼後中心格即上車 cell。
  k = 同一 epoch 內、上車 cell 相同的請求數（含自己）。
- 駕駛：每班一個假名、每 30 s 一次心跳；可用駕駛 = 600 s 內有下車事件（Phase 0 供給模型）。
  k = 同一 30 s 批次窗內、心跳 cell 相同的可用駕駛數（含自己）。
  （駕駛同一 epoch 內同一假名本來就可連結，見 Table 6 same-epoch AUC 1.0；這裡量的是
   攻擊者在某一個時間點拿 cell 去對應「是哪一個人」時的候選數。）
- 連結成功率上界：攻擊者在下一期看到同一 cell，只能在 k 個候選中猜，成功率 1/k；
  報 mean(1/k) 為「目標每次都回到同一 cell」這個最有利攻擊者假設下的期望成功率。

輸出：out/anonymity_set.json
"""
import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
P0 = HERE.parent / "phase0"
sys.path.insert(0, str(P0))
import config as C  # noqa: E402

EPOCH_S = 3600          # 預設 epoch = 1 h（Section 6.1）
BATCH_S = C.BATCH_WINDOW_S
AVAIL_S = C.DRIVER_AVAIL_WINDOW_S


def _sec(s):
    """datetime 欄 -> Unix 秒（不依賴 pandas 內部時間單位）。"""
    return pd.to_datetime(s).values.astype("datetime64[s]").astype("int64")


def summarize(k):
    k = np.asarray(k, dtype=float)
    return {
        "n_uploads": int(k.size),
        "k_median": float(np.median(k)),
        "k_p5": float(np.percentile(k, 5)),
        "k_p25": float(np.percentile(k, 25)),
        "frac_k1": round(float(np.mean(k == 1)), 4),     # 解碼後即唯一可識別
        "frac_k_le5": round(float(np.mean(k <= 5)), 4),
        "mean_link_success": round(float(np.mean(1.0 / k)), 4),
    }


def rider_k(reqs, g):
    ep = _sec(reqs["pu_ts"]) // EPOCH_S
    key = pd.DataFrame({"ep": ep, "gx": reqs[f"pu_gx_{g}"], "gy": reqs[f"pu_gy_{g}"]})
    return key.groupby(["ep", "gx", "gy"])["ep"].transform("size").values


def driver_k(sup, g):
    """每個 30 s 批次窗取可用駕駛快照（600 s 內有下車），算同 cell 人數。"""
    t = _sec(sup["time"])
    gx = sup[f"gx_{g}"].values; gy = sup[f"gy_{g}"].values
    order = np.argsort(t); t, gx, gy = t[order], gx[order], gy[order]
    ks = []
    for w in range(int(t.min() // BATCH_S) * BATCH_S, int(t.max()) + 1, BATCH_S):
        lo, hi = np.searchsorted(t, w - AVAIL_S), np.searchsorted(t, w)
        if hi - lo == 0:
            continue
        cells = pd.Series(list(zip(gx[lo:hi], gy[lo:hi])))
        ks.append(cells.map(cells.value_counts()).values)
    return np.concatenate(ks)


def main():
    reqs = pd.read_parquet(C.CLEAN / "trips_grid.parquet")
    sup = pd.read_parquet(C.CLEAN / "driver_supply.parquet")
    out = {"epoch_s": EPOCH_S, "batch_s": BATCH_S, "avail_s": AVAIL_S,
           "n_requests": len(reqs), "n_supply": len(sup), "grids": {}}
    print(f"E7b 匿名集合（epoch={EPOCH_S}s，攻擊者知每期 salt、逐次解碼）")
    for g in C.GRID_SIZES:
        r = summarize(rider_k(reqs, g)); d = summarize(driver_k(sup, g))
        out["grids"][str(g)] = {"rider": r, "driver": d}
        for name, s in (("乘客", r), ("駕駛", d)):
            print(f"  grid={g:>3}m {name}: k 中位數 {s['k_median']:.0f}，p5 {s['k_p5']:.0f}，"
                  f"k=1 佔 {s['frac_k1']:.1%}，k≤5 佔 {s['frac_k_le5']:.1%}，"
                  f"連結成功率上界 {s['mean_link_success']:.3f}")
    dst = HERE / "out" / "anonymity_set.json"
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"-> {dst}")


if __name__ == "__main__":
    main()
