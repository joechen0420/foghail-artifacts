# phase4 — QBFT chain deployment

Deploys the FogHailAttestation contract on a 4-node Hyperledger Besu QBFT permissioned
chain and measures confirmation latency, throughput, gas, and on-chain bytes
(paper Table 8). Needs Java 21 and Besu 25.4.1 (binaries not included; setup steps in
BESU_SETUP.zh.md).

## v4 contract (current manuscript)

`contracts/FogHailAttestation.sol` (v4) implements:

- `registerRoot` (registrar only) and `openBatch(B)`: requires root reputation R ≥ θ and a zero
  outstanding count, and grants the batch a budget of 3B partial signatures;
- `logIssue(root, h, auth)` / `logReceipt(p, h, auth)`: called by a registered validator before it
  answers a blind session; the contract checks the budget (or at most three receipt partials per
  settled pseudonym) and the holder's signature over `authDigest(kind, ctx, validator, h)`, h = H(R, e);
- `attestAndSettle`: unchanged from v3 (fog-node match signature, a 3-of-4 credential per party,
  both rating signatures, ΔR computed by the contract, each trip and pseudonym settled once);
- `deposit`: receipts with serial H(root ‖ r) recomputed from the depositor, unused credentials with a
  pseudonym possession signature; the outstanding count is kept in partial signatures;
- `rollEpoch`: salt beacon, salt_e = H(blockhash_{b-1} ‖ e).

```
pip install web3 psutil py-solc-x ecdsa eth-utils eth-abi eth-account
FOGHAIL_NETDIR=networkFiles1s FOGHAIL_AFFINITY=1 FOGHAIL_SUF=_v4 python -u run_e6_v4.py
```

`run_e6_v4.py` first runs the protocol and audit checks on the live chain (`protocol_checks` in
`out/e6_v4_summary.json`), then measures sequential submission (200 tx) and open-loop submission at
5/10/20/50 tx/s (300 tx each); `out/e6_v4_raw.json` holds every transaction. `FOGHAIL_LATENCY=0`
runs only the protocol part (`out/e6_v4_protocol_summary.json`).

## Earlier versions

- v3: `contracts/archive/FogHailAttestation_v3.sol`, `run_e6_v3.py` (uses the archived
  `../phase5/foghail_cred_v3.py`), results `out/e6_v3_*.json`. Its settlement path is identical to v4.
- v1: `run_e6_local.py`, results `out/e6_results*.json` (about 0.5 tx/s regardless of the nominal rate).
