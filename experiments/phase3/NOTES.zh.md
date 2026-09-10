# Phase 3 — BRIP COR2Vec 嵌入媒合（表 1 BRIP 列、圖 4、E4 反推）

重建 BRIP(以位置嵌入做語意媒合)當 baseline,量其媒合品質、揭露「嵌入距離非單調」與「嵌入可被反推還原位置」。

## 產生論文的哪些數據

- **表 1（BRIP 列）**:以 COR2Vec 嵌入 cosine 相似度選駕駛的 Hit@1、接駕中位、膨脹比。
- **圖 4**:地理距離 vs 嵌入相似度的**非單調性**(BRIP 沉重膨脹尾的根因)。
- **隱私攻擊表（BRIP 列，對到 §6.4）**:E4 嵌入反推——攻擊者握公開模型即可 ~100% 還原精確 cell。

## 檔案

| 檔 | 用途 |
|---|---|
| `corpus.py` | 把 OSM 路網轉成位置 token 句(同 Phase 0 投影) |
| `skipgram.py` | 輕量 skip-gram（負採樣）位置嵌入,**忠實替代 BRIP 的 gensim FastText** |
| `train_cor2vec.py` | 訓練嵌入,存 `out/cor2vec.npz` |
| `embed_lookup.py` | 座標→嵌入向量查詢 |
| `experiment_brip.py` | BRIP 嵌入媒合品質(→ 表 1 BRIP 列) |
| `fig4_nonmonotonic.py` | 圖 4:距離-相似度非單調 |
| `e4_inversion.py` | E4 嵌入反推攻擊(還原率/誤差) |
| `run_all.py` | 一鍵:訓練 → 媒合 → 圖 4 → 反推 |
| `data/nyc_roads_major.json` | **已附** OSM 主要道路路網(Overpass 抓取,曼哈頓 40.70–40.80N),`corpus.py` 的輸入 |
| `out/` | **已附訓練好的嵌入 `cor2vec.npz` 與結果** |

## 資料夾擺法(必讀)

`config.py` 會到**上一層的 `phase0/`** 載入 Phase 0 的設定與資料路徑,所以**不能只解壓這一包就跑**。請把 phase0 套件與本套件的 `src` 內容改名並列成:

```
任意資料夾/
├─ phase0/          ← 「phase0_資料前處理與Oracle」套件 src/ 的內容
│   └─ data/clean/  ← 跑過 phase0 後產生(trips_grid.parquet、driver_supply.parquet)
└─ phase3/          ← 本套件 src/ 的內容
    ├─ data/nyc_roads_major.json   (已附)
    └─ out/cor2vec.npz             (已附)
```

之後一律在 `phase3/` 底下執行指令。只想取表 1/圖 4 的既有數字,直接讀 `out/phase3_results.json` 即可,什麼都不用擺。

## 相依

```
pip install numpy scipy matplotlib
```

## 執行

```
python run_all.py            # 訓練→媒合→圖4→反推（需 Phase 0 資料;OSM 路網已附於 data/）
# out/cor2vec.npz 已附，可跳過訓練直接跑後續：
python experiment_brip.py
python fig4_nonmonotonic.py
python e4_inversion.py
```

## 備註（重要,誠實揭露）

- **Python 3.14 無法安裝 gensim**(scipy `triu` 衝突),故以**自寫 skip-gram＋負採樣**忠實替代 BRIP COR2Vec 的本質(共現式位置嵌入,路網相鄰 cell 在向量空間相近);**未建模 FastText 的子詞特徵**。
- 這一包就是你先前指的「BRIP COR2Vec 嵌入模型」。
