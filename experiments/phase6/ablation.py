# -*- coding: utf-8 -*-
"""消融實驗 §6.7：量測「非對稱編碼」的效益（其餘消融數據已於 E7/表5 取得）。

非對稱（預設）：駕駛編 1 格、乘客編 9 格 → 判定 driver bits ⊆ rider BF。
對稱（移除非對稱）：雙方都編 9 格 → 判定 popcount(BF_d AND BF_p) ≥ k。
對「非相鄰」的 cell 對量偽陽率，顯示對稱編碼使 FPR 大幅疊加（§4.2.1 設計理由）。
"""
import sys
import importlib.util
from pathlib import Path
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
_bp = Path(__file__).resolve().parent.parent / "phase1" / "bloom.py"
_s = importlib.util.spec_from_file_location("bloom", _bp)
_b = importlib.util.module_from_spec(_s); _s.loader.exec_module(_b)
BF = _b.BF

M, K, SALT = 512, 5, "foghail-epoch-0"
rng = np.random.default_rng(42)


def neigh(gx, gy):
    return [(gx + dx, gy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]


def far_cell(c, span=10000, min_gap=5):
    while True:
        d = (int(rng.integers(0, span)), int(rng.integers(0, span)))
        if abs(d[0] - c[0]) > min_gap or abs(d[1] - c[1]) > min_gap:
            return d


def measure(trials=6000):
    bf = BF(M, K, SALT)
    fp_asym = fp_sym = 0
    for _ in range(trials):
        rc = (int(rng.integers(0, 10000)), int(rng.integers(0, 10000)))
        bf_p = bf.build(neigh(*rc))                 # 乘客 9 格
        dcell = far_cell(rc)                         # 非相鄰駕駛
        # 非對稱：駕駛 1 格，測 ⊆
        dmask = bf.cell_bits(dcell)
        if (dmask & bf_p) == dmask:
            fp_asym += 1
        # 對稱：駕駛也編 9 格，測 C_int ≥ k
        bf_d9 = bf.build(neigh(*dcell))
        if (bf_d9 & bf_p).bit_count() >= K:
            fp_sym += 1
    return fp_asym / trials, fp_sym / trials


def main():
    import json
    fa, fs = measure()
    print("§6.7 消融：非對稱編碼 vs 對稱編碼（m=512, k=5）")
    print(f"  非對稱（預設）偽陽率 = {fa:.2e}")
    print(f"  對稱（移除非對稱）偽陽率 = {fs:.2e}")
    print(f"  對稱使 FPR 增加約 {fs/max(fa,1e-9):.0f}× " if fa > 0 else f"  對稱 FPR={fs:.2e}（非對稱≈0）")
    out = {"asymmetric_fpr": fa, "symmetric_fpr": fs}
    (Path(__file__).resolve().parent / "out").mkdir(exist_ok=True)
    json.dump(out, open(Path(__file__).resolve().parent / "out" / "ablation.json",
              "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
