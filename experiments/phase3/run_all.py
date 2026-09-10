# -*- coding: utf-8 -*-
"""Phase 3 一鍵：訓練 COR2Vec -> 嵌入媒合(表1 BRIP列) -> 圖4 -> E4 反推。"""
import sys
import json
import config as C
import train_cor2vec
from experiment_brip import run_brip
import fig4_nonmonotonic
import e4_inversion

sys.stdout.reconfigure(encoding="utf-8")


def main():
    print("===== 1) 訓練 COR2Vec =====")
    train_cor2vec.main()

    print("\n===== 2) BRIP 嵌入媒合品質（表1 BRIP 列） =====")
    brip = run_brip()
    for k, v in brip.items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    print("\n===== 3) 圖4：距離–相似度非單調性 =====")
    corr = fig4_nonmonotonic.main()

    print("\n===== 4) E4：嵌入反推攻擊 =====")
    inv = e4_inversion.main()

    out = {
        "brip_matching": brip,
        "fig4_pearson_r": corr,
        "e4_inversion": [{"noise": nl, "exact_recovery": ex, "err_median_m": er}
                         for nl, ex, er in inv],
    }
    (C.OUT / "phase3_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完成 -> {C.OUT/'phase3_results.json'}")


if __name__ == "__main__":
    main()
