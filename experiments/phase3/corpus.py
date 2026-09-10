# -*- coding: utf-8 -*-
"""把 OSM 路網（ways=節點序列）轉成位置 token 句子，供 COR2Vec 訓練。
token = 以 TOKEN_GRID 公尺網格量化後的 cell「gx_gy」（用 Phase 0 同一投影）。
"""
import sys
import json
import numpy as np
import config as C

sys.stdout.reconfigure(encoding="utf-8")


def point_token(lat, lon):
    x, y = C.to_meters(np.array([lat]), np.array([lon]))
    gx = int(np.floor(x[0] / C.TOKEN_GRID))
    gy = int(np.floor(y[0] / C.TOKEN_GRID))
    return f"{gx}_{gy}", (gx, gy)


def _road_graph():
    """由 OSM ways 建 cell 鄰接圖，回傳 (adj, cell_xy)。"""
    data = json.load(open(C.DATA / "nyc_roads_major.json", encoding="utf-8"))
    adj, cell_xy = {}, {}
    for el in data.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        seq = []
        for nd in el["geometry"]:
            tok, cell = point_token(nd["lat"], nd["lon"])
            if tok not in cell_xy:
                cell_xy[tok] = ((cell[0] + 0.5) * C.TOKEN_GRID,
                                (cell[1] + 0.5) * C.TOKEN_GRID)
            if not seq or seq[-1] != tok:
                seq.append(tok)
        for a, b in zip(seq, seq[1:]):
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
    return adj, cell_xy


def build_sentences(seed=C.RANDOM_SEED):
    """在路網圖上做隨機漫步，產生長句以強化共現訊號。"""
    adj, cell_xy = _road_graph()
    rng = np.random.default_rng(seed)
    nodes = [n for n in adj if adj[n]]
    sentences = []
    for start in nodes:
        for _ in range(C.WALKS_PER_NODE):
            walk = [start]
            cur = start
            for _ in range(C.WALK_LEN - 1):
                nbrs = list(adj[cur])
                if not nbrs:
                    break
                cur = nbrs[int(rng.integers(len(nbrs)))]
                walk.append(cur)
            sentences.append(walk)
    return sentences, cell_xy


if __name__ == "__main__":
    s, cxy = build_sentences()
    ntok = sum(len(x) for x in s)
    print(f"隨機漫步句={len(s):,}  總 token={ntok:,}  唯一 cell={len(cxy):,}")
