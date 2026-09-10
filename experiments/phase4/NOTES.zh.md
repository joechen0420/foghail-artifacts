# Phase 4 — 許可鏈 QBFT 鏈上效能（表 4）

在實際運作的 4 節點 Hyperledger Besu QBFT 許可鏈上部署存證/信譽合約,量測確認延遲、gas、鏈上位元組。**這是最重的一包,需 Java 21 + Besu 環境。**

## 產生論文的哪些數據

- **表 4**:確認延遲 p50/p95(隔離部署 2.0/3.9 s、同置 5.9/8.0 s)、交易大小/gas(268 B / 96,355)、鏈上 bytes/行程(164 B calldata / ~96 B 狀態)。

## 檔案

| 檔 | 用途 |
|---|---|
| `contracts/FogHailAttestation.sol` | **智能合約**:存證(`attestAndSettle` 寫 {TripHash, 時間戳})＋雙邊信譽更新 |
| `run_e6_local.py` | **單機起 4 節點 Besu QBFT(不需 Docker,Java 21 直跑)→ 部署合約 → 送交易量測** |
| `bench_e6.py` / `bench_e6_cloud.py` | 量測 harness(本機 / 多主機各節點 RPC) |
| `besu_watchdog.py` | Besu 看門狗(僅針對 besu 的 java 行程,記憶體/時限超標自動關閉) |
| `qbft-genesis.json` / `qbft-config*.json` | QBFT 創世與出塊設定(1s / 2s 出塊) |
| `docker-compose.yml` | (選配)以 Docker 起節點 |
| `README.md` | phase4 原始操作說明 |
| `out/` | **已附合約 ABI/BIN、部署位址、既有量測結果**(e6_results*.json) |

## 相依

```
pip install web3 psutil
```
**外部需求**:Java 21（JDK）＋ Hyperledger Besu 25.4.1（本機無 Docker 時用 Java 直接跑;`run_e6_local.py` 會啟動節點）。

## 執行

```
# 需先安裝 Java 21 與 Besu（見 README.md 取得 Besu）
python run_e6_local.py       # 起 4 節點 QBFT → 部署合約 → 送 attestAndSettle → 量測
```
兩種組態:①**同置**(4 節點共用一機,2s 出塊);②**CPU 隔離**(以 CPU 親和性把各驗證者釘到專屬核心,1s 出塊穩定、p50 降到 2.0 s)。

## 備註

- **Besu 執行檔與節點資料因體積大不進版控**,需自行下載 Besu(見 `README.md`)。`out/` 已附既有量測結果,想直接看數字可讀 `out/e6_results*.json`。
- 同置的延遲膨脹純屬 CPU 資源競爭假影,非 QBFT 協定限制(§5.4)。
