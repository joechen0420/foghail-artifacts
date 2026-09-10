# phase4 — QBFT chain deployment

Deploys the FogHailAttestation contract (attestation + two-sided reputation) on a
4-node Hyperledger Besu QBFT permissioned chain and measures confirmation latency,
gas, and on-chain bytes (paper Table 6). The heaviest artifact: needs Java 21 and
Besu 25.4.1 (binaries not included; setup steps in BESU_SETUP.zh.md). Measured results are shipped
in `out/e6_results*.json`.

```
pip install web3 psutil
python run_e6_local.py       # start 4 nodes -> deploy -> benchmark
```
