# -*- coding: utf-8 -*-
"""Phase 0 全域參數。Phase 1+ 掃描時只改這裡。"""
from pathlib import Path
import math

# ---- 路徑 ----
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = DATA / "raw"
CLEAN = DATA / "clean"
GT = DATA / "ground_truth"
for d in (RAW, CLEAN, GT):
    d.mkdir(parents=True, exist_ok=True)

# ---- 資料來源（NYC Open Data，2015 Yellow Taxi，含經緯度） ----
SOCRATA_DATASET = "2yzn-sicd"
SOCRATA_URL = f"https://data.cityofnewyork.us/resource/{SOCRATA_DATASET}.json"
# 欄位名（此資料集用 pickup_datetime，非 tpep_）
COL_PU_LAT, COL_PU_LON = "pickup_latitude", "pickup_longitude"
COL_DO_LAT, COL_DO_LON = "dropoff_latitude", "dropoff_longitude"
COL_PU_TS, COL_DO_TS = "pickup_datetime", "dropoff_datetime"
COL_DIST = "trip_distance"  # 英里

# ---- 開發樣本抓取範圍（跑通管線用；正式實驗再擴大） ----
SAMPLE_START = "2015-06-01T07:00:00"
SAMPLE_END = "2015-06-01T10:00:00"   # 早尖峰 3 小時
PAGE_SIZE = 50000

# ---- NYC 邊界框（曼哈頓 + 內城；水面/離群點過濾） ----
LON_MIN, LON_MAX = -74.05, -73.70
LAT_MIN, LAT_MAX = 40.60, 40.90

# ---- 本地等距投影參考點（NYC 質心） ----
LAT0 = (LAT_MIN + LAT_MAX) / 2.0
LON0 = (LON_MIN + LON_MAX) / 2.0
_M_PER_DEG_LAT = 110540.0
_M_PER_DEG_LON = 111320.0 * math.cos(math.radians(LAT0))

def to_meters(lat, lon):
    """經緯度 -> 本地公尺平面 (x, y)。lat/lon 可為純量或 numpy array。"""
    x = (lon - LON0) * _M_PER_DEG_LON
    y = (lat - LAT0) * _M_PER_DEG_LAT
    return x, y

# ---- 清洗門檻 ----
MIN_TRIP_M = 100.0          # 行程 < 100 m 視為雜訊
MAX_TRIP_HOURS = 6.0        # 時長 > 6 hr 視為異常
MIN_MILE = MIN_TRIP_M / 1609.34

# ---- 網格 ----
GRID_SIZES = [100, 250, 500]   # 公尺
DEFAULT_GRID = 250
NEIGHBORHOOD = 9               # 乘客擴展 3x3

# ---- 時間窗與駕駛供給 ----
BATCH_WINDOW_S = 30            # 媒合批次窗
DRIVER_AVAIL_WINDOW_S = 600    # 下車後多久內視為可用駕駛
RHO = 1.0                      # 可用駕駛抽樣密度（1.0=全用）

# ---- Oracle ----
TOPK = [1, 3, 5]
RADII_M = [500, 1000]

RANDOM_SEED = 42
