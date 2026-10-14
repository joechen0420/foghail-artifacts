# FogHail — Code and Measurement Artifacts

Source code and experiment scripts accompanying the manuscript:

> **FogHail: A Fog-Assisted Privacy-Preserving Ride-Hailing System with Two-Sided
> Unlinkable Reputation on a Permissioned Blockchain**
> Ming-Chiao Chen, Yu Wei Tung — National Taitung University, Taiwan
> (submitted to *Journal of Network and Computer Applications*, 2026)

The repository covers the four artifact groups cited in the paper's Data availability
statement — blind matching, ORide/BRIP baselines, smartphone benchmarks, and the QBFT
chain deployment — plus the attack/ablation suite and supporting reference code.

## Repository map

Table and figure numbers follow the current manuscript (revision of 2026-10-14).

| Directory | Contents | Reproduces (paper) |
|---|---|---|
| `experiments/phase0` | NYC data download, cleaning, driver-supply model, plaintext oracle | §6.1 dataset statistics; ground truth for Table 3 |
| `experiments/phase1` | **Blind matching**: salted-Bloom-filter fog matcher, matching quality, winner selection, FPR and grid sweeps | Table 3 (FogHail rows), Table 4, Table 5 (fog side), Figs. 3–4 |
| `experiments/phase2` | **ORide baseline**: Paillier reconstruction of the encrypted-distance protocol (SHE figures from published SEAL numbers) | Table 3 (ORide row), Table 5 (ORide row) |
| `experiments/phase3` | **BRIP baseline**: COR2Vec-style location embedding (skip-gram over the OSM road network), embedding inversion | Table 3 (BRIP row), Fig. 5, embedding-inversion row of Table 6 |
| `experiments/phase4` | **QBFT deployment**: 4-node Hyperledger Besu chain; **v3 settlement contract** (root registry, batch opening, single settlement entry verifying 3-of-4 validator blind signatures, receipt deposit, roll-epoch salt beacon); latency harness | Table 8 |
| `experiments/phase5` | **3-of-4 validator blind-signature credentials** (`foghail_cred.py`): threshold Schnorr blind signatures on secp256k1, ROS guard, receipts, batch accounting; client-cost benchmark; v1.0 single-issuer reference kept for comparison | Table 7 (estimated column) |
| `experiments/phase6` | Privacy attacks (dictionary, harvesting, bit-pattern linkage AUC), **anonymity set after decoding**, ablations | Table 6, Table 9 |
| `experiments/e5v3_kotlin` | Kotlin port of the 3-of-4 credential for on-device measurement, JVM tests, Python cross-check of phone output | Table 7 (to replace the estimate with a handset measurement) |
| `mobile-benchmark` | **Smartphone benchmarks** (Kotlin, BouncyCastle): client-side encoding (E3) and single-session credential operations (E5) on a real handset | Table 5 (client side), Table 7 (measured column) |
| `fog-node` | Standalone fog-node matcher: the same blind-matching core, runnable on any PC/Raspberry Pi | Fog-side latency spot-checks |

## What changed in v1.1

v1.0 (`v1.0-submission`) shipped a single-issuer Schnorr blind-signature credential on
secp256r1 and a contract without on-chain credential verification. v1.1 adds the
reputation protocol described in the revised manuscript (§4.4):

- **3-of-4 validator blind signatures**: each of the four chain validators holds its own
  issuing key; a credential is valid only with blind signatures from three of them, so no
  single party can issue one. Each validator serves one blind session at a time (ROS guard).
- **On-chain settlement**: one call verifies the fog node's match signature, 2 × 3
  validator signatures, and both rating signatures; each trip and each pseudonym settles
  once; the contract computes ΔR itself.
- **Reputation carry-over**: blind-signed receipts per ΔR denomination are deposited to
  the root identity; a new batch opens only after the previous one is fully accounted for,
  so negative receipts cannot be dropped.
- **Salt beacon**: `rollEpoch` derives the epoch salt from the previous block hash.
- **Re-run chain measurements** (sequential and open-loop 5/10/20/50 tx/s, per-transaction
  records released) and the **anonymity-set experiment** behind the revised G2 argument.

v1.0 files are kept unchanged; the earlier contracts are in `experiments/phase4/contracts/archive/`.

Each directory ships its own `README.md` (run instructions) and, where applicable,
precomputed results under `out/` so every reported number can be inspected without
re-running anything. `NOTES.zh.md` files are extended notes in Chinese.

## Requirements

```
pip install numpy pandas scipy matplotlib pyarrow requests ecdsa eth-utils scikit-learn
```

- Python 3.10+ (developed on 3.14).
- `experiments/phase4` additionally needs Java 21, Hyperledger Besu 25.4.1, and
  `pip install web3 psutil py-solc-x` (see its README; the Besu binaries are not included).
- `mobile-benchmark` builds in Android Studio against a physical Android 9+ handset
  (see its README).

## Layout constraint (do not rename)

`phase1/2/3/4/6` and `e5v3_kotlin` load configuration and shared modules from their **sibling**
directories (`../phase0`, `../phase1`, `../phase5`), so the `experiments/phase*` folder names must
stay as they are, and scripts must be run from inside their own directory.

## Reproducing the pipeline

1. **Data** (once): in `experiments/phase0`, run `python download.py` then
   `python run_all.py`. This pulls the NYC TLC Yellow Taxi 2015-06 sample from
   [NYC Open Data](https://data.cityofnewyork.us/) and builds `data/clean/` and the
   plaintext-oracle ground truth. Raw data is not redistributed here.
2. **Blind matching**: in `experiments/phase1`, `python run_all.py` (tables data),
   `python plots.py` (Figs. 2–3; works directly from the shipped `out/` CSVs).
3. **Baselines**: `experiments/phase2` → `python oride_ref.py`;
   `experiments/phase3` → `python run_all.py` (a trained embedding
   `out/cor2vec.npz` and the OSM road network are included, so the training step can
   be skipped).
4. **Attacks/ablation**: in `experiments/phase6`, `python attacks.py` and
   `python ablation.py`; `python anonymity_set.py` for the anonymity set.
5. **Credentials**: in `experiments/phase5`, `python bench_v3_client.py` (3-of-4
   protocol self-check and client cost).
6. **On-device numbers**: build `mobile-benchmark` and press the three on-screen
   buttons (bit-level cross-check against the Python reference must pass first);
   for the 3-of-4 credential, see `experiments/e5v3_kotlin`.
7. **Chain**: follow `experiments/phase4/README.md`.

## Honest-disclosure notes

- ORide's SHE latency/bandwidth figures are the values published with SEAL
  (USENIX Sec'17); the encrypted-distance protocol itself is independently
  reconstructed with Paillier additive HE and verified exact (phase2).
- The BRIP embedding is a faithful skip-gram re-implementation of COR2Vec's
  co-occurrence objective; FastText subword features are not modeled (phase3).
- The 3-of-4 credential cost on the handset (Table 7) is currently scaled from a
  desktop ratio; `experiments/e5v3_kotlin` is the harness for measuring it directly.
- Details of each simplification are recorded in the per-directory notes.

## License and citation

Released under the MIT License (see `LICENSE`). If you use this code, please cite
the manuscript above.
