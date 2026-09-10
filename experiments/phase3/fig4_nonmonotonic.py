# -*- coding: utf-8 -*-
"""圖 4：重現 BRIP 的「地理距離 vs 嵌入 cosine 相似度」非單調性。
抽樣大量 cell 對，畫散佈與分箱平均±標準差，顯示相似度不隨距離單調遞減。"""
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config as C
from embed_lookup import Cor2Vec

sys.stdout.reconfigure(encoding="utf-8")
FIGS = Path(__file__).resolve().parent.parent.parent / "figures"


def main(n_pairs=40000, seed=C.RANDOM_SEED):
    cv = Cor2Vec()
    rng = np.random.default_rng(seed)
    V = len(cv.tokens)
    a = rng.integers(0, V, n_pairs)
    b = rng.integers(0, V, n_pairs)
    m = a != b
    a, b = a[m], b[m]
    dist = np.linalg.norm(cv.xy[a] - cv.xy[b], axis=1)
    sim = (cv.emb[a] * cv.emb[b]).sum(1)
    keep = dist <= 5000
    dist, sim = dist[keep], sim[keep]

    # 分箱平均
    bins = np.linspace(0, 5000, 26)
    bi = np.digitize(dist, bins)
    xs, ms, ss = [], [], []
    for k in range(1, len(bins)):
        s = sim[bi == k]
        if len(s) > 20:
            xs.append((bins[k - 1] + bins[k]) / 2); ms.append(s.mean()); ss.append(s.std())
    xs, ms, ss = map(np.array, (xs, ms, ss))

    corr = np.corrcoef(dist, sim)[0, 1]
    import os
    en = os.environ.get("LANG_EN") == "1"
    plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "Noto Sans TC", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(figsize=(6, 4.2))
    ax.scatter(dist[::5], sim[::5], s=2, alpha=0.06, color="#64748b")
    ax.plot(xs, ms, "-o", color="#e11d48", ms=4,
            label="binned mean" if en else "分箱平均")
    ax.fill_between(xs, ms - ss, ms + ss, color="#e11d48", alpha=0.15,
                    label="±1 std" if en else "±1 標準差")
    ax.set_xlabel("geographic distance (m)" if en else "地理距離（公尺）")
    ax.set_ylabel("embedding cosine similarity" if en else "嵌入 cosine 相似度")
    ax.set_title((f"Fig. 4. BRIP embedding: distance–similarity non-monotonicity (Pearson r={corr:.2f})"
                  if en else f"圖 4. BRIP 嵌入：距離–相似度非單調性（Pearson r={corr:.2f}）"))
    ax.grid(True, ls=":", alpha=0.4)
    ax.legend(fontsize=8)
    fig.tight_layout()
    p = FIGS / ("fig4_nonmonotonic_en.png" if en else "fig4_nonmonotonic.png")
    fig.savefig(p, dpi=200)
    print(f"Pearson r = {corr:.3f} -> {p}")
    return corr


if __name__ == "__main__":
    main()
