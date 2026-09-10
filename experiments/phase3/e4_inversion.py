# -*- coding: utf-8 -*-
"""E4：嵌入反推攻擊。攻擊者握有公開 COR2Vec 模型，看到一個位置嵌入即可
以最近向量查表還原其 cell（位置）。量測還原率與還原誤差。

對照組：本文 FogHail 的加鹽 BF 為單向且每 epoch 輪換，無此反推能力。
"""
import sys
import numpy as np
import config as C
from embed_lookup import Cor2Vec

sys.stdout.reconfigure(encoding="utf-8")


def main(n=5000, noise_levels=(0.0, 0.05, 0.1, 0.2), seed=C.RANDOM_SEED):
    cv = Cor2Vec()
    rng = np.random.default_rng(seed)
    V = len(cv.tokens)
    targets = rng.integers(0, V, n)
    E = cv.emb                              # (V,d) 已 L2 正規化
    print(f"詞典（可還原位置）大小 V={V:,}，TOKEN_GRID={C.TOKEN_GRID} m")
    rows = []
    for nl in noise_levels:
        vecs = E[targets].copy()
        if nl > 0:
            vecs = vecs + rng.normal(0, nl, vecs.shape)
            vecs /= (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)
        # 最近向量查表（cosine，皆正規化 → 內積最大）
        sims = vecs @ E.T                  # (n,V)
        pred = sims.argmax(1)
        exact = (pred == targets).mean()
        err = np.linalg.norm(cv.xy[pred] - cv.xy[targets], axis=1)
        rows.append((nl, exact, np.median(err)))
        print(f"  雜訊σ={nl:>4}: 精確還原率={exact:6.1%}  位置誤差中位數={np.median(err):6.1f} m")
    return rows


if __name__ == "__main__":
    main()
