# -*- coding: utf-8 -*-
"""輕量 skip-gram（負採樣）位置嵌入，忠實替代 BRIP 的 gensim FastText。

BRIP 的 COR2Vec 本質：把地理位置當「詞」，以路網共現（同一條路上的相鄰節點）
訓練 dense 向量，鄰近位置嵌入相近。此處以 skip-gram + 負採樣重現同一機制，
沿用 BRIP 參數 vec=50/window=5/lr=0.5。（FastText 另有子詞 n-gram；因環境無法
編譯 gensim，改用 word-level skip-gram，並於論文說明此替代。）
"""
import numpy as np


class SkipGram:
    def __init__(self, vec_size=50, window=5, lr=0.5, neg=5,
                 epochs=5, min_count=1, seed=42):
        self.vs, self.win, self.lr = vec_size, window, lr
        self.neg, self.epochs, self.min_count = neg, epochs, min_count
        self.rng = np.random.default_rng(seed)

    def build_vocab(self, sentences):
        from collections import Counter
        cnt = Counter(t for s in sentences for t in s)
        self.vocab = [w for w, c in cnt.items() if c >= self.min_count]
        self.w2i = {w: i for i, w in enumerate(self.vocab)}
        V = len(self.vocab)
        freq = np.array([cnt[w] for w in self.vocab], dtype=np.float64)
        p = freq ** 0.75
        self.neg_p = p / p.sum()
        # Xavier 初始化
        self.W = (self.rng.random((V, self.vs)) - 0.5) / self.vs
        self.C = np.zeros((V, self.vs))
        return V

    def _pairs(self, sentences):
        pairs = []
        for s in sentences:
            ids = [self.w2i[t] for t in s if t in self.w2i]
            for i, c in enumerate(ids):
                w = self.rng.integers(1, self.win + 1)
                for j in range(max(0, i - w), min(len(ids), i + w + 1)):
                    if j != i:
                        pairs.append((c, ids[j]))
        return np.array(pairs, dtype=np.int64)

    def train(self, sentences):
        import sys
        self.build_vocab(sentences)
        pairs = self._pairs(sentences)
        V = len(self.vocab)
        print(f"  vocab={V:,} pairs={len(pairs):,}", flush=True)
        for ep in range(self.epochs):
            self.rng.shuffle(pairs)
            lr = self.lr * (1 - ep / (self.epochs + 1))
            loss = 0.0
            for b in range(0, len(pairs), 4096):
                batch = pairs[b:b + 4096]
                ctr, ctx = batch[:, 0], batch[:, 1]
                neg = self.rng.choice(V, size=(len(batch), self.neg), p=self.neg_p)
                vc = self.W[ctr]                              # (B,d)  中心詞
                uo = self.C[ctx]                              # (B,d)  正樣本
                un = self.C[neg]                              # (B,neg,d) 負樣本
                pos_s = 1 / (1 + np.exp(-(vc * uo).sum(1)))   # σ(vc·uo)
                neg_s = 1 / (1 + np.exp(-(un * vc[:, None]).sum(2)))  # σ(vc·un)
                loss += -(np.log(pos_s + 1e-9).sum()
                          + np.log(1 - neg_s + 1e-9).sum())
                # 梯度
                g_uo = (pos_s - 1)[:, None] * vc              # (B,d)
                g_un = neg_s[:, :, None] * vc[:, None, :]      # (B,neg,d)
                g_vc = ((pos_s - 1)[:, None] * uo
                        + (neg_s[:, :, None] * un).sum(1))     # (B,d)
                # 以 add.at 累加（索引可能重複）
                np.subtract.at(self.C, ctx, lr * g_uo)
                np.subtract.at(self.C, neg.ravel(),
                               lr * g_un.reshape(-1, self.vs))
                np.subtract.at(self.W, ctr, lr * g_vc)
            print(f"  epoch {ep+1}/{self.epochs} loss/pair={loss/max(len(pairs),1):.4f}", flush=True)
        # L2 正規化，供 cosine
        self.E = self.W / (np.linalg.norm(self.W, axis=1, keepdims=True) + 1e-9)
        return self

    def vec(self, token):
        i = self.w2i.get(token)
        return self.E[i] if i is not None else None
