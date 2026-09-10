# Phase 4 — Besu QBFT 私有鏈（存證＋雙邊信譽）

本目錄為 **可直接部署** 的 4 節點 Besu QBFT 私有鏈與 FogHail 合約；E6 數字需在有 Docker 的機器（或 EC2 t3.medium ×4）實跑。

## 檔案

- `contracts/FogHailAttestation.sol`：存證（`attestTrip`）＋雙邊信譽（`settleTrip`）＋合併（`attestAndSettle`）。鏈上僅存 TripHash 與假名信譽，明細密文留本地。
- `qbft-genesis.json`：QBFT 創世檔，`blockperiodseconds=2`（對應 <3s 確認目標）。
- `docker-compose.yml`：4 節點容器。
- `bench_e6.py`：E6 量測 harness（送 `attestAndSettle`，量確認延遲 p50/p95、TPS、bytes）。

## 部署步驟（在有 Docker 的機器）

```bash
# 1. 產生 4 個 validator 金鑰與 extraData
besu operator generate-blockchain-config \
  --config-file=qbft-config.json --to=networkFiles --private-key-file-name=key
# 2. 把產生的 validator extraData 填入 qbft-genesis.json；key 放各節點目錄
# 3. 啟動 4 節點
docker compose up -d
# 4. 編譯部署合約（Foundry 或 Remix→Ganache 皆可）
forge create contracts/FogHailAttestation.sol:FogHailAttestation \
  --rpc-url http://localhost:8545 --private-key $DEPLOYER_KEY
# 5. 量測
pip install web3
python bench_e6.py --contract 0x<addr> --key $DEPLOYER_KEY --tps 10 --n 200
python bench_e6.py --contract 0x<addr> --key $DEPLOYER_KEY --tps 50 --n 500
python bench_e6.py --contract 0x<addr> --key $DEPLOYER_KEY --tps 100 --n 1000
```

## 鏈上成本精算（不需跑鏈，已可填論文）

`attestAndSettle(bytes32,bytes32,bytes32,int256,int256)`：
- **calldata**：4（selector）+ 5×32（參數）= **164 bytes/行程**
- **鏈上狀態寫入**：`tripExists`（1 slot=32 B）＋ 兩筆 `reputation`（2 slot=64 B）= **~96 B/行程**
- 對照 BRIP：132 B/請求（僅存 IPFS 雜湊，無信譽）——FogHail 存證部分相當，且多含雙邊信譽更新。

## 待實跑（E6）

- 確認延遲 p50/p95（QBFT block period 2s → 設計目標 p50 ≈ 1–2s、<3s；需實測確認）
- TPS 飽和點（10/50/100 TPS 掃描）
- 4 節點跨 EC2 的實際網路確認延遲
