# Phase 0 — 資料前處理與明文 Oracle（ground truth）

所有媒合實驗的**資料基礎**。下載 NYC 計程車資料、清洗投影網格化、建駕駛供給模型、算明文 Oracle,並產出論文 §6.1 的資料統計。

## 產生論文的哪些數據

- **§6.1 資料統計**(請求/供給數、每窗請求數、可用駕駛池、500 m/1 km 內有車比例、最近駕駛距離、網格占用)。
- **表 1 的 ground truth**:明文 Oracle 對每筆請求算 top-k 最近可用駕駛——後面 phase1/2/3 的 Hit@k、接駕膨脹比都以此為對照。

## 檔案

| 檔 | 用途 |
|---|---|
| `download.py` | 從 NYC Open Data（Socrata API）分頁下載 2015 Yellow Taxi 樣本 |
| `preprocess.py` | 清洗 + 本地等距投影（度→公尺）+ 網格化 |
| `driver_supply.py` | 駕駛供給模型:把每個下車事件視為「一位駕駛於該時刻在該點變為可用」 |
| `oracle.py` | 明文 Oracle:每筆請求的 top-k 最近可用駕駛與半徑內駕駛數 |
| `stats.py` | 產 §6.1 資料統計表 |
| `run_all.py` | 一鍵串接 preprocess → driver_supply → oracle → stats |
| `config.py` | 服務區邊界、投影原點、網格大小、批次窗等參數 |

## 資料夾擺法(必讀)

本包是其他包的**基礎**:phase1、phase2、phase3、phase6 的程式會到**與自己同層的 `phase0/`** 載入本包的 `config.py` 與資料。因此解壓後請把本包的 `src` 內容放進名為 **`phase0`** 的資料夾,與其他 phase 並列:

```
任意資料夾/
├─ phase0/   ← 「phase0_資料前處理與Oracle」套件 src/ 的內容
│   └─ data/clean/、data/ground_truth/  ← 跑過 phase0 後產生
└─ phase1/、phase2/、phase3/、phase6/ …(各包 src/ 的內容,依需要擺)
```

之後各 phase 一律在自己的資料夾底下執行指令。


## 相依

```
pip install numpy pandas scipy pyarrow requests
```

## 執行

```
python download.py            # 先下載原始資料到 data/raw/
python run_all.py             # preprocess → driver_supply → oracle → stats
# 或一次到底：
python run_all.py --download
```

## 備註

- 原始資料與 ground truth 檔（parquet / npz）**因體積大不進版控**,需用 `download.py` 自行下載重建。
- 論文用 **2015-06** 樣本(2016-07 之後 NYC 只釋出 taxi-zone ID、無精確座標)。
- 駕駛供給模型的限制(資料集無車輛 ID、無法串同車連續行程)論文 §6.1 已誠實揭露。
