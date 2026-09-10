# -*- coding: utf-8 -*-
"""產出圖 2（FPR 理論vs實測）與圖 3（grid 品質/可行率權衡），存到 ../../figures/。
LANG=en 產英文版（fig2_fpr_en.png / fig3_grid_tradeoff_en.png）。"""
import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import config as C

sys.stdout.reconfigure(encoding="utf-8")
FIGS = Path(__file__).resolve().parent.parent.parent / "figures"
FIGS.mkdir(exist_ok=True)

EN = os.environ.get("LANG_EN") == "1"
SUF = "_en" if EN else ""
NO_TITLE = os.environ.get("FIG_NO_TITLE") == "1"   # 去掉圖內嵌標題（改由文件圖說呈現）
L = {
    "fig2_title_zh": r"圖 2. BF 偽陽率：理論 $(1-e^{-kn/m})^k$ vs 實測（n=9）",
    "fig2_title_en": r"Fig. 2. Bloom-filter FPR: theoretical $(1-e^{-kn/m})^k$ vs. measured (n=9)",
    "fig2_x_zh": "雜湊函數個數 k", "fig2_x_en": "number of hash functions k",
    "fig2_y_zh": "偽陽率 FPR（對數軸）", "fig2_y_en": "false-positive rate (log scale)",
    "theo_zh": "理論", "theo_en": "theory", "meas_zh": "實測", "meas_en": "measured",
    "fig3_title_zh": "圖 3. 網格粒度的品質/可行率/隱私權衡",
    "fig3_title_en": "Fig. 3. Grid-granularity quality/availability/privacy trade-off",
    "fig3_x_zh": "網格邊長 grid_size（公尺）", "fig3_x_en": "grid size (meters)",
    "fig3_y_zh": "比例", "fig3_y_en": "ratio",
    "match_zh": "媒合可行率", "match_en": "match rate",
    "infl_zh": "接駕膨脹比 p50", "infl_en": "pickup-dist. inflation p50",
}
def t(key): return L[f"{key}_en"] if EN else L[f"{key}_zh"]


def fig2_fpr():
    df = pd.read_csv(C.OUT / "fpr_sweep.csv")
    fig, ax = plt.subplots(figsize=(6, 4.2))
    colors = {256: "#e11d48", 512: "#0e7490", 1024: "#047857"}
    for m in sorted(df["m"].unique()):
        d = df[df["m"] == m].sort_values("k")
        ax.plot(d["k"], d["theoretical"], "-", color=colors[m], label=f"m={m} {t('theo')}")
        emp = d["empirical"].replace(0, np.nan)
        ax.plot(d["k"], emp, "o", color=colors[m], mfc="white", label=f"m={m} {t('meas')}")
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda y, _: r"$10^{%d}$" % round(np.log10(y))))
    ax.set_xlabel(t("fig2_x")); ax.set_ylabel(t("fig2_y"))
    if not NO_TITLE: ax.set_title(t("fig2_title"))
    ax.grid(True, which="both", ls=":", alpha=0.4)
    ax.legend(fontsize=7, ncol=3)
    fig.tight_layout()
    p = FIGS / f"fig2_fpr{SUF}.png"; fig.savefig(p, dpi=200); print(f"-> {p}")


def fig3_grid():
    df = pd.read_csv(C.OUT / "grid_sweep.csv").sort_values("grid")
    fig, ax1 = plt.subplots(figsize=(6, 4.2))
    x = df["grid"]
    ax1.plot(x, df["hit@1"], "o-", color="#0e7490", label="Hit@1")
    ax1.plot(x, df["hit@3"], "s-", color="#0891b2", label="Hit@3")
    ax1.plot(x, df["match_rate"], "^--", color="#047857", label=t("match"))
    ax1.set_xlabel(t("fig3_x")); ax1.set_ylabel(t("fig3_y")); ax1.set_ylim(0, 1)
    ax2 = ax1.twinx()
    ax2.plot(x, df["infl_p50"], "d-", color="#e11d48", label=t("infl"))
    ax2.set_ylabel(t("infl"), color="#e11d48")
    ax2.tick_params(axis="y", labelcolor="#e11d48")
    ax1.set_xticks(list(x))
    if not NO_TITLE: ax1.set_title(t("fig3_title"))
    l1, la1 = ax1.get_legend_handles_labels()
    l2, la2 = ax2.get_legend_handles_labels()
    ax1.legend(l1 + l2, la1 + la2, fontsize=8, loc="center right")
    fig.tight_layout()
    p = FIGS / f"fig3_grid_tradeoff{SUF}.png"; fig.savefig(p, dpi=200); print(f"-> {p}")


if __name__ == "__main__":
    plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "Noto Sans TC", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["mathtext.fontset"] = "dejavusans"
    fig2_fpr()
    fig3_grid()
