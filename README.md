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

| Directory | Contents | Reproduces (paper) |
|---|---|---|
| `experiments/phase0` | NYC data download, cleaning, driver-supply model, plaintext oracle | §6.1 dataset statistics; ground truth for Table 1 |
| `experiments/phase1` | **Blind matching**: salted-Bloom-filter fog matcher, matching quality, FPR sweeps | Table 1 (FogHail rows), Table 2, Table 3 (fog side), Figs. 2–3 |
| `experiments/phase2` | **ORide baseline**: Paillier reconstruction of the encrypted-distance protocol (SHE figures from published SEAL numbers) | Table 1 (ORide row), Table 3 (ORide columns) |
| `experiments/phase3` | **BRIP baseline**: COR2Vec-style location embedding (skip-gram over the OSM road network), embedding inversion | Table 1 (BRIP row), Fig. 4, embedding-inversion row of Table 4 |
| `experiments/phase4` | **QBFT deployment**: 4-node Hyperledger Besu chain, attestation/reputation contract, latency harness | Table 6 |
| `experiments/phase5` | ACL one-show anonymous credential, Python reference (cross-checks the Kotlin build) | Table 5 (cross-check) |
| `experiments/phase6` | Privacy attacks (dictionary, harvesting, linkage AUC) and ablations | Table 4, Table 7 |
| `mobile-benchmark` | **Smartphone benchmarks** (Kotlin, BouncyCastle): client-side encoding (E3) and credential operations (E5) on a real handset | Table 3 (client side), Table 5 |
| `fog-node` | Standalone fog-node matcher: the same blind-matching core, runnable on any PC/Raspberry Pi | Fog-side latency spot-checks |

Each directory ships its own `README.md` (run instructions) and, where applicable,
precomputed results under `out/` so every reported number can be inspected without
re-running anything. `NOTES.zh.md` files are extended notes in Chinese.

## Requirements

```
pip install numpy pandas scipy matplotlib pyarrow requests ecdsa scikit-learn
```

- Python 3.10+ (developed on 3.14).
- `experiments/phase4` additionally needs Java 21, Hyperledger Besu 25.4.1, and
  `pip install web3 psutil` (see its README; the Besu binaries are not included).
- `mobile-benchmark` builds in Android Studio against a physical Android 9+ handset
  (see its README).

## Layout constraint (do not rename)

`phase1/2/3/6` load configuration and shared modules from their **sibling**
directories (`../phase0`, `../phase1`), so the `experiments/phase*` folder names must
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
   `python ablation.py`.
5. **On-device numbers**: build `mobile-benchmark` and press the three on-screen
   buttons (bit-level cross-check against the Python reference must pass first).
6. **Chain**: follow `experiments/phase4/README.md`.

## Honest-disclosure notes

- ORide's SHE latency/bandwidth figures are the values published with SEAL
  (USENIX Sec'17); the encrypted-distance protocol itself is independently
  reconstructed with Paillier additive HE and verified exact (phase2).
- The BRIP embedding is a faithful skip-gram re-implementation of COR2Vec's
  co-occurrence objective; FastText subword features are not modeled (phase3).
- Details of each simplification are recorded in the per-directory notes.

## License and citation

Released under the MIT License (see `LICENSE`). If you use this code, please cite
the manuscript above.
