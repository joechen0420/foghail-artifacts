# -*- coding: utf-8 -*-
"""訓練 COR2Vec（skip-gram 替代），存嵌入與 cell 中心到 out/cor2vec.npz。"""
import sys
import numpy as np
import config as C
from corpus import build_sentences
from skipgram import SkipGram

sys.stdout.reconfigure(encoding="utf-8")


def main():
    print("建語料 …")
    sents, cell_xy = build_sentences()
    print(f"  ways={len(sents):,} 總token={sum(len(s) for s in sents):,} 唯一cell={len(cell_xy):,}")
    print(f"訓練 skip-gram (vec={C.VEC_SIZE}, window={C.WINDOW}, lr={C.LR}, epochs={C.EPOCHS}) …")
    sg = SkipGram(vec_size=C.VEC_SIZE, window=C.WINDOW, lr=C.LR,
                  neg=C.NEG, epochs=C.EPOCHS, min_count=C.MIN_COUNT,
                  seed=C.RANDOM_SEED).train(sents)
    toks = np.array(sg.vocab)
    xy = np.array([cell_xy[t] for t in sg.vocab])
    np.savez(C.OUT / "cor2vec.npz", tokens=toks, emb=sg.E, xy=xy)
    print(f"完成 -> {C.OUT/'cor2vec.npz'}（{len(toks):,} 個 cell 嵌入）")


if __name__ == "__main__":
    main()
