# -*- coding: utf-8 -*-
"""Phase 3（BRIP 嵌入媒合重建）參數。沿用 Phase 0 資料。"""
import importlib.util
from pathlib import Path

_p0 = Path(__file__).resolve().parent.parent / "phase0" / "config.py"
_spec = importlib.util.spec_from_file_location("phase0_config", _p0)
C0 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C0)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "out"
for d in (DATA, OUT):
    d.mkdir(exist_ok=True)

CLEAN = C0.CLEAN
to_meters = C0.to_meters
BATCH_WINDOW_S = C0.BATCH_WINDOW_S
DRIVER_AVAIL_WINDOW_S = C0.DRIVER_AVAIL_WINDOW_S
TOPK = C0.TOPK

# ---- COR2Vec（BRIP 參數；FastText→以 skip-gram 忠實替代） ----
TOKEN_GRID = 50         # 位置 token 網格（公尺）
VEC_SIZE = 50           # BRIP: vector size 50
WINDOW = 5              # BRIP: window 5
LR = 0.5                # BRIP: learning rate 0.5
EPOCHS = 3
NEG = 5                 # 負採樣數
MIN_COUNT = 1           # BRIP: min_count 1
# 路網圖隨機漫步（強化共現訊號，node2vec 式）
WALKS_PER_NODE = 6
WALK_LEN = 15

RANDOM_SEED = 42
MAX_REQUESTS = 8000
