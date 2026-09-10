# -*- coding: utf-8 -*-
"""載入 COR2Vec 嵌入，並提供「任意投影座標(x,y) -> 嵌入向量」的查詢
（先量化到 token；OOV 則以 KDTree 找最近的已知 cell 中心）。"""
import numpy as np
from scipy.spatial import cKDTree
import config as C


class Cor2Vec:
    def __init__(self, npz_path=None):
        d = np.load(npz_path or (C.OUT / "cor2vec.npz"), allow_pickle=True)
        self.tokens = d["tokens"]
        self.emb = d["emb"]                       # (V, dim) 已 L2 正規化
        self.xy = d["xy"]                         # (V, 2) cell 中心（公尺）
        self.tok2i = {t: i for i, t in enumerate(self.tokens)}
        self._tree = cKDTree(self.xy)

    def token_of(self, x, y):
        gx = int(np.floor(x / C.TOKEN_GRID)); gy = int(np.floor(y / C.TOKEN_GRID))
        return f"{gx}_{gy}"

    def idx_of_xy(self, x, y):
        """回傳最能代表 (x,y) 的 cell 索引：先查精確 token，OOV 則最近鄰。"""
        i = self.tok2i.get(self.token_of(x, y))
        if i is not None:
            return i
        _, j = self._tree.query([x, y])
        return int(j)

    def vec_xy(self, x, y):
        return self.emb[self.idx_of_xy(x, y)]
