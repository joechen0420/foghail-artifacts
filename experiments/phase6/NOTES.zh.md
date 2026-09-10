# Phase 6 — 隱私攻擊與消融實驗（隱私攻擊表、消融表）

以實測方式驗證系統的隱私保證與各設計元素的必要性。

## 產生論文的哪些數據

- **隱私攻擊表（§6.4）**:字典攻擊(知鹽/鹽已輪換)的 cell 還原率、位置蒐割所需查詢數、**假名連結 AUC**(跨 epoch 0.495 vs 同 epoch 1.0)。
- **消融表（§6.7 / §5.4）**:移除各設計元素的影響——salt 輪換(AUC 0.495→1.0)、非對稱編碼(假陽率 ≈0→0.30)、信譽驗證、班次級假名。

## 檔案

| 檔 | 用途 |
|---|---|
| `attacks.py` | 字典攻擊(知鹽還原 cell)、salt 輪換使字典失效、位置蒐割查詢數、**假名連結 AUC**(跨/同 epoch) |
| `ablation.py` | 逐一移除設計元素,量受影響指標 |
| `out/` | **已附跑好的結果**(phase6_attacks.json、ablation.json) |

## 資料夾擺法(必讀)

`attacks.py` 會到**上一層的 `phase0/`** 載入資料路徑、`attacks.py` 與 `ablation.py` 都要**上一層的 `phase1/bloom.py`**(BF 編碼核心),所以**不能只解壓這一包就跑**。請把三包的 `src` 內容改名並列成:

```
任意資料夾/
├─ phase0/   ← 「phase0_資料前處理與Oracle」套件 src/ 的內容
│   └─ data/clean/、data/ground_truth/  ← 跑過 phase0 後產生
├─ phase1/   ← 「phase1_BF盲媒合」套件 src/ 的內容
└─ phase6/   ← 本套件 src/ 的內容(out/ 已附結果)
```

之後一律在 `phase6/` 底下執行指令。只想取攻擊表/消融表的既有數字,直接讀已附的 `out/*.json` 即可,什麼都不用擺。


## 相依

```
pip install numpy pandas scikit-learn
```
（AUC 用 `sklearn.metrics.roc_auc_score`。）

## 執行

```
# 需 Phase 0 / Phase 1 的基礎（BF 編碼與資料）
python attacks.py            # 產隱私攻擊表數據
python ablation.py           # 產消融表數據
```
> `out/` 已附論文用的結果,可直接讀 JSON 取數字。

## 備註

- **假名連結 AUC = 0.495**(接近隨機猜測 0.5)是本系統「跨 epoch 不可連結」的關鍵證據;移除 salt 輪換後 AUC 飆到 1.0,證明其必要性。
- ⚠️ 論文審稿風險(供參):AUC 只對抗**這支腳本用的連結模型**;更強的軌跡側信道攻擊未涵蓋,可在文中誠實標注為未來工作(見先前的 §4.3 討論)。
