# -*- coding: utf-8 -*-
"""Phase 1（BF 盲媒合）參數。沿用 Phase 0 的資料與網格。"""
import importlib.util
from pathlib import Path

# 依路徑載入 phase0 的 config（避免與本檔同名衝突），共用資料路徑與網格
_p0 = Path(__file__).resolve().parent.parent / "phase0" / "config.py"
_spec = importlib.util.spec_from_file_location("phase0_config", _p0)
C0 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C0)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

CLEAN = C0.CLEAN
GRID_SIZES = C0.GRID_SIZES
DEFAULT_GRID = C0.DEFAULT_GRID
BATCH_WINDOW_S = C0.BATCH_WINDOW_S
DRIVER_AVAIL_WINDOW_S = C0.DRIVER_AVAIL_WINDOW_S
TOPK = C0.TOPK
to_meters = C0.to_meters

# ---- 布隆過濾器 ----
M_DEFAULT = 512          # 位元長度
K_DEFAULT = 5            # 雜湊數
SALT = "foghail-epoch-0" # 單一 epoch 固定（salt 輪換是 Phase 6 消融）
M_SWEEP = [256, 512, 1024]
K_SWEEP = [3, 4, 5, 6, 7]

# ---- 勝出策略 ----
STRATEGIES = ["first_come", "max_bits", "weighted_random"]

RANDOM_SEED = 42
# 為求速度，E2 可抽樣請求數（None=全用）
MAX_REQUESTS = 8000
