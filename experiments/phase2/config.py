# -*- coding: utf-8 -*-
"""Phase 2（ORide 重建）參數。沿用 Phase 0 資料、Phase 1 的 BF。"""
import importlib.util
from pathlib import Path

def _load(name, rel):
    p = Path(__file__).resolve().parent.parent / rel
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

C0 = _load("phase0_config", "phase0/config.py")

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"; OUT.mkdir(exist_ok=True)
CLEAN = C0.CLEAN
BATCH_WINDOW_S = C0.BATCH_WINDOW_S
DRIVER_AVAIL_WINDOW_S = C0.DRIVER_AVAIL_WINDOW_S
TOPK = C0.TOPK

# BF（與 Phase 1 一致）
M_DEFAULT = 512
K_DEFAULT = 5
SALT = "foghail-epoch-0"

# ORide 已核實發表值（USENIX Sec 17；環境 Intel i5-4200U 2.6GHz/6GB）
ORIDE_CIPHERTEXT_KB = 186        # 乘客每請求下載單一密文
ORIDE_SP_MS_AT_4096 = 208.9      # S2 優化，n=4096 駕駛
ORIDE_ROUNDS = 2                 # ≥2（乘客↔SP、SP↔駕駛）

RANDOM_SEED = 42
