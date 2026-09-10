# -*- coding: utf-8 -*-
"""圖 2 資料：BF 偽陽率 實測 vs 理論 (1-e^(-kn/m))^k，掃描 (m,k)。
受控實驗：乘客插入 9 格（隨機 cell），對大量「非成員」cell 測試是否偽陽。
"""
import sys
import numpy as np
import pandas as pd
import config as C
from bloom import BF, theoretical_fpr

sys.stdout.reconfigure(encoding="utf-8")


def empirical_fpr(m, k, n=9, trials=4000, seed=C.RANDOM_SEED):
    rng = np.random.default_rng(seed + m * 31 + k)
    fp = 0
    span = 10000
    for _ in range(trials):
        member_cells = [(int(rng.integers(0, span)), int(rng.integers(0, span)))
                        for _ in range(n)]
        bf = BF(m, k, C.SALT)
        bf_p = bf.build(member_cells)
        mem = set(member_cells)
        while True:
            nc = (int(rng.integers(0, span)), int(rng.integers(0, span)))
            if nc not in mem:
                break
        dmask = bf.cell_bits(nc)
        if (dmask & bf_p) == dmask:   # 成員測試意義下的偽陽
            fp += 1
    return fp / trials


def main():
    rows = []
    for m in C.M_SWEEP:
        for k in C.K_SWEEP:
            emp = empirical_fpr(m, k)
            th = theoretical_fpr(m, k, n=9)
            rows.append({"m": m, "k": k, "empirical": emp, "theoretical": th})
            print(f"m={m} k={k}: 實測 {emp:.2e} 理論 {th:.2e}")
    df = pd.DataFrame(rows)
    df.to_csv(C.OUT / "fpr_sweep.csv", index=False)
    print(f"-> {C.OUT/'fpr_sweep.csv'}")


if __name__ == "__main__":
    main()
