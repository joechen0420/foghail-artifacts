# phase4 — QBFT chain deployment

Deploys the FogHailAttestation contract on a 4-node Hyperledger Besu QBFT permissioned
chain and measures confirmation latency, throughput, gas, and on-chain bytes
(paper Table 8). Needs Java 21 and Besu 25.4.1 (binaries not included; setup steps in
BESU_SETUP.zh.md).

## v3 contract (current manuscript)

`contracts/FogHailAttestation.sol` (v3) implements:

- `registerRoot` (registrar only) and `openBatch` (requires root reputation R ≥ θ and the
  previous batch fully accounted for);
- `attestAndSettle`, the single settlement entry: fog-node match signature, a 3-of-4
  validator Schnorr blind-signature credential for each party, both rating signatures,
  ΔR computed by the contract, each trip and each pseudonym settled once;
- `deposit`: receipts carried back to the root identity, unused credentials returned;
- `rollEpoch`: salt beacon, salt_e = H(blockhash_{b-1} ‖ e).

Schnorr signatures on secp256k1 are verified with a single `ecrecover`, because the
challenge commits to the address of the nonce point. The protocol reference
implementation is `../phase5/foghail_cred.py`. v1 and v2 sources are in
`contracts/archive/`.

```
pip install web3 psutil py-solc-x ecdsa eth-utils
FOGHAIL_NETDIR=networkFiles1s FOGHAIL_AFFINITY=1 FOGHAIL_SUF=_v3 python -u run_e6_v3.py
```

`run_e6_v3.py` first runs 18 protocol checks on the live chain, then measures
sequential submission (200 tx) and open-loop submission at 5/10/20/50 tx/s (300 tx each).
A separate thread records the block in which each transaction first appears; signed
transactions are forwarded to all four validators, one ordered stream per validator.
Outputs: `out/e6_v3_summary.json` (checks, gas per operation, per-rate statistics) and
`out/e6_v3_raw.json` (every transaction). `run_e6_v2.py` holds the shared block watcher
and open-loop sender.

Two pitfalls: web3's `get_block` fails on QBFT blocks (extraData > 32 B), so the raw
`eth_getBlockByNumber` RPC is used; Besu lacks `eth_getRawTransactionByHash`, so the
transaction size is taken from the submitted raw transaction.

## v1.0 harness (kept for reference)

```
python run_e6_local.py       # start 4 nodes -> deploy -> benchmark (v1 contract)
```

The v1 harness waited for each confirmation before sending the next transaction
(about 0.5 tx/s regardless of the nominal rate, 40 tx per rate); its results are
`out/e6_results*.json` and are superseded by the v3 measurements above.
