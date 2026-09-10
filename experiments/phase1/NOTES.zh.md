# Phase 1 — 布隆過濾器盲媒合（表 1、表 2、圖 2、圖 3）

FogHail 的核心媒合實驗:霧節點在加鹽布隆過濾器上做盲測媒合,量媒合品質、延遲、假陽率、網格權衡。

## 產生論文的哪些數據

- **表 1（本系統列）**:Hit@1、接駕膨脹比 p50/p95、接駕距離中位數(grid=250 與 grid=100)。
- **表 2**:霧端媒合延遲(0.28 ms @ 池=1000)、通訊量 64 B、互動輪數。
- **圖 2**:BF 假陽率 實測 vs 理論 (1−e^(−kn/m))^k。
- **圖 3**:網格粒度對命中率／可行率／膨脹比的權衡。

## 檔案

| 檔 | 用途 |
|---|---|
| `bloom.py` | **霧節點媒合器核心**:加鹽 BF(Python 大整數位元陣列)、AND、成員測試 |
| `experiment_e2.py` | E2 媒合品質:對照明文 Oracle 算 Hit@k、膨脹比、可行率(→ 表 1、表 2、圖 3 資料) |
| `fpr_sweep.py` | 圖 2 資料:BF 假陽率 實測 vs 理論,掃描 (m,k) |
| `plots.py` | 由 CSV 產出**圖 2、圖 3**(存到 `figures/`);`LANG_EN=1` 產英文版 |
| `measure_client_encoding.py` | E3 用戶端編碼延遲(參考平台;手機端見「乘客與駕駛端 App」包) |
| `run_all.py` | 一鍵:E2 + FPR 掃描,存 CSV/JSON |
| `config.py` | m、k、grid、鄰域、批次窗等參數 |
| `out/` | **已附跑好的結果**(e2_results.json、fpr_sweep.csv、grid_sweep.csv) |

## 資料夾擺法(必讀)

`config.py` 與 `measure_client_encoding.py` 會到**上一層的 `phase0/`** 載入 Phase 0 的設定與資料路徑,所以**不能只解壓這一包就跑**。請把 phase0 套件與本套件的 `src` 內容改名並列成:

```
任意資料夾/
├─ phase0/   ← 「phase0_資料前處理與Oracle」套件 src/ 的內容
│   └─ data/clean/、data/ground_truth/  ← 跑過 phase0 後產生
└─ phase1/   ← 本套件 src/ 的內容(out/ 已附結果)
```

之後一律在 `phase1/` 底下執行指令。只想取表 1/表 2/圖 2/圖 3 的既有數字或重畫圖,直接用已附的 `out/`(`python plots.py`)即可,phase0 只需 `config.py` 在位、不必重跑資料。


## 相依

```
pip install numpy pandas scipy matplotlib ecdsa
```

## 執行

```
# 需先有 Phase 0 的 ground truth（明文 Oracle 輸出）
python run_all.py            # 產 out/ 的 CSV/JSON（表1/表2/圖2/圖3 資料）
python plots.py              # 由 CSV 產出 figures/fig2、fig3（中文版）
LANG_EN=1 python plots.py    # 產英文版 fig2_fpr_en、fig3_grid_tradeoff_en
```

> `out/` 已附論文用的結果,可直接 `python plots.py` 重畫圖,不必重跑 E2。

## 備註

- 媒合判定用**精確成員測試** `(BF_d AND BF_p)==BF_d`(避免早期 `C_int≥k` 因雜湊內部碰撞造成的 3.2% 偽陰)。
- `bloom.py` 與「乘客與駕駛端 App」的 Kotlin 版、以及「霧節點 PC 版」是同一套邏輯。
