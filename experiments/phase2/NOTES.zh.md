# Phase 2 — ORide 重建（表 1 ORide 列、表 2 對照）

重建 ORide(同態加密叫車)當 baseline,證明其媒合品質＝明文 Oracle,並重現其位置洩漏攻擊面;同時量 FogHail 霧端延遲供對照。

## 產生論文的哪些數據

- **表 1（ORide 列）**:ORide 在密文上算精確平方歐氏距離、乘客解密選最近,故品質＝明文 Oracle(Hit@1=1.0、膨脹=1.0)。
- **表 2（ORide 對照）**:SHE 密文 186 KB／請求、SP 208.9 ms＠4096、互動輪數 ≥2;對照 FogHail 的 64 B／0.28 ms／1 輪。

## 檔案

| 檔 | 用途 |
|---|---|
| `oride_ref.py` | 做三件事:①確認 ORide 品質＝Oracle;②以 Paillier 加法同態**重建加密距離協定**(算出精確平方距離、重現 Kumaraswamy 位置蒐割攻擊面);③量 FogHail 霧端 BF 媒合延遲與通訊量 |
| `config.py` | ORide 發表值(密文 KB、SP ms、輪數)等參數 |

## 資料夾擺法(必讀)

`config.py` 會到**上一層的 `phase0/`** 載入 Phase 0 的設定與資料,`oride_ref.py` 另需**上一層的 `phase1/bloom.py`**(量 FogHail 霧端對照延遲),所以**不能只解壓這一包就跑**。請把三包的 `src` 內容改名並列成:

```
任意資料夾/
├─ phase0/   ← 「phase0_資料前處理與Oracle」套件 src/ 的內容
│   └─ data/clean/、data/ground_truth/  ← 跑過 phase0 後產生
├─ phase1/   ← 「phase1_BF盲媒合」套件 src/ 的內容
└─ phase2/   ← 本套件 src/ 的內容
```

之後一律在 `phase2/` 底下執行指令。


## 相依

```
pip install numpy pandas scipy
```

## 執行

```
python oride_ref.py
```

## 備註（重要,誠實揭露）

- **Python 3.14 無法安裝 Microsoft SEAL / tenseal**,故 ORide 的 **SHE 延遲/頻寬採其論文發表的 SEAL 數字**(見 config)。
- 加密距離協定改用 **Paillier 加法同態**獨立重建,確認算出的是**精確**平方距離(最大誤差 0)——這重現了「乘客只得到(排列後)距離」的攻擊面,支撐 §6.4 的位置蒐割討論。
- 這一包就是你先前指的「ORide SEAL/SHE 重建」。
