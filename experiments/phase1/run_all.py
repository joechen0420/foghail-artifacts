# -*- coding: utf-8 -*-
"""Phase 1 一鍵：跑 E2（表1/表2/圖3 資料）+ FPR 掃描（圖2 資料），存 CSV/JSON。"""
import sys
import json
import pandas as pd
import config as C
from experiment_e2 import run_e2
import fpr_sweep

sys.stdout.reconfigure(encoding="utf-8")


def main():
    results = {}

    # ---- 表 1：預設參數（成員測試判定） ----
    print("\n[表1] 預設 grid=250, m=512, k=5, weighted_random …")
    t1 = run_e2()
    results["table1_default"] = t1
    print("  ", {kk: round(v, 4) if isinstance(v, float) else v for kk, v in t1.items()})

    # 論文判定式 C_int>=k 的偽陰（記錄用）
    print("[附註] 論文原判定式 C_int>=k 的偽陰率 …")
    thr = run_e2(decision="threshold", insitu_fp_windows=0)
    results["threshold_fnr_note"] = {"bf_fnr": thr["bf_fnr"]}
    print(f"   C_int>=k 偽陰率 = {thr['bf_fnr']:.4f}（成員測試則為 {t1['bf_fnr']:.4f}）")

    # ---- 表 2：勝出策略 ----
    print("\n[表2] 勝出策略比較 …")
    t2 = []
    for s in C.STRATEGIES:
        r = run_e2(strategy=s, insitu_fp_windows=0)
        t2.append({"strategy": s, "hit@1": r["hit@1"],
                   "infl_p50": r["infl_p50"], "infl_p95": r["infl_p95"]})
        print(f"   {s}: Hit@1={r['hit@1']:.3f} 膨脹 p50={r['infl_p50']:.2f} p95={r['infl_p95']:.2f}")
    results["table2_strategies"] = t2

    # ---- 圖 3：grid 掃描 ----
    print("\n[圖3] grid 掃描 …")
    g = []
    for grid in C.GRID_SIZES:
        r = run_e2(grid=grid, insitu_fp_windows=10)
        g.append({"grid": grid, "match_rate": r["match_rate"],
                  "hit@1": r["hit@1"], "hit@3": r["hit@3"],
                  "infl_p50": r["infl_p50"], "infl_p95": r["infl_p95"],
                  "bf_fpr_insitu": r["bf_fpr_insitu"]})
        print(f"   grid={grid}: match={r['match_rate']:.3f} Hit@1={r['hit@1']:.3f} "
              f"Hit@3={r['hit@3']:.3f} 膨脹p50={r['infl_p50']:.2f}")
    results["fig3_grid_sweep"] = g
    pd.DataFrame(g).to_csv(C.OUT / "grid_sweep.csv", index=False)

    # ---- 圖 2：FPR 掃描 ----
    print("\n[圖2] FPR 理論 vs 實測掃描 …")
    fpr_sweep.main()

    (C.OUT / "e2_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成 -> {C.OUT/'e2_results.json'}")


if __name__ == "__main__":
    main()
