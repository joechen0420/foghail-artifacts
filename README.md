# FogHail — Code and Measurement Artifacts

Source code and experiment scripts accompanying the manuscript:

> **Privacy-Preserving Ride-Hailing with Fog-Assisted Proximity Matching and
> Blockchain-Based Anonymous Reputation**
> Ming-Chiao Chen, Reen-Cheng Wang, Chun-Yi Tsai, Yu Wei Tung — National Taitung University, Taiwan
> (submitted to *Journal of Network and Computer Applications*, 2026)

The repository covers the four artifact groups cited in the paper's Data availability
statement — blind matching, ORide/BRIP baselines, smartphone benchmarks, and the QBFT
chain deployment — plus the attack/ablation suite and supporting reference code.

## Repository map

Table and figure numbers follow the submitted manuscript (revision of 2026-11-03).

| Directory | Contents | Reproduces (paper) |
|---|---|---|
| `experiments/phase0` | NYC data download, cleaning, driver-supply model, plaintext oracle | §6.1 dataset statistics; ground truth for Table 4 |
| `experiments/phase1` | **Blind matching**: salted-Bloom-filter fog matcher, matching quality, winner selection, FPR and grid sweeps | Table 4 (FogHail rows), winner-selection comparison in §6.2, Table 5 (fog side), Figs. 3–4 |
| `experiments/phase2` | **ORide baseline**: Paillier reconstruction of the encrypted-distance protocol (SHE figures from published SEAL numbers) | Table 4 (ORide row), Table 5 (ORide column) |
| `experiments/phase3` | **BRIP baseline**: COR2Vec-style location embedding (skip-gram over the OSM road network), embedding inversion | Table 4 (BRIP row), Fig. 5, embedding-lookup result in §6.4 |
| `experiments/phase4` | **QBFT deployment**: 4-node Hyperledger Besu chain; **v4 contract** (root registry, batch opening with an on-chain partial-signature budget, holder-authorized issuance and receipt logs, single settlement entry verifying 3-of-4 validator blind signatures, root-bound receipt deposit, roll-epoch salt beacon); protocol checks and latency harness | Table 8 |
| `experiments/phase5` | **3-of-4 validator blind-signature credentials** (`foghail_cred.py`, v4): threshold Schnorr blind signatures on secp256k1, ROS guard, on-chain issuance budget, holder authorization, persisted session nonces, root-bound receipts; adversarial test suite; client-cost benchmark; v3 and v1.0 references kept for comparison | Python reference for the protocol timed in Table 7 |
| `experiments/phase6` | Privacy attacks (dictionary, harvesting, bit-pattern linkage AUC), **anonymity set after decoding**, ablations | Table 6; driver nine-cell ablation in §4.2 |
| `experiments/e5v3_kotlin` | Measurement app (Kotlin): the 3-of-4 credential and v4 authorization signature, plus button ⑦ for the pseudonym-key comparison of v1.3; JVM tests, Python cross-check of phone output | Table 7 (Galaxy Tab A measured column and Redmi scaled column) |
| `mobile-benchmark` | **Smartphone benchmarks** (Kotlin, BouncyCastle): client-side encoding (E3), pseudonym-key derivation, and single-session credential operations (E5) on a real handset; raw phone results in `results/` | Table 5 (client side), §6.3 precomputed-key measurement, Table 7 (single-session column) |
| `fog-node` | Standalone fog-node matcher: the same blind-matching core, runnable on any PC/Raspberry Pi | Fog-side latency spot-checks |

## What changed in v1.3

v1.3 aligns the handset code with the key derivation described in the paper (§4.3, §5.1). Protocol,
contracts, and all other measurements are unchanged.

- **Derived request-signing key**: up to v1.2, `FogHailBloom.derivePseudonym` drew a fresh random
  secp256r1 key on each call. It now derives sk = SHA-256(root ‖ t as 8-byte big-endian) mod n, the
  same construction as the settlement key, and computes pk = sk·G.
- **Precomputed mode**: the key depends only on the root key and the trip index t, so the client can
  derive it while idle after the previous trip. `E3LatencyBench.run(..., keyMode)` now accepts
  `"random"` (the v1.2 behaviour), `"derived"` (derivation inside the timed region), and
  `"precomputed"` (derivation before t0, timed separately as `T_derive`).
- **Measurement**: button ⑦ of the app in `experiments/e5v3_kotlin` first checks the derived key
  against the Python value, then alternates the three modes for three rounds each. Two runs on a Galaxy
  Tab A 8.0 (SM-T295, Android 9) are in `mobile-benchmark/results/`; `check_e3_result.py` summarizes
  them. With the key precomputed, encoding plus signature took 0.95× the fresh-random-key latency
  (1.65 vs. 1.73 ms median), and derivation itself took 16.7 ms median. The Redmi figure in Table 5
  (0.70 ms) was measured with the fresh random key and therefore bounds the request path from above.

## What changed in v1.2

v1.2 answers a code audit of the v1.1 issuance logic (protocol v4). Settlement is unchanged.

- **Shared issuance budget**: v1.1 let each validator sign B times per batch, so mixing signer subsets
  yielded up to 4B/3 credentials. v1.2 gives each batch an on-chain budget of 3B partial signatures;
  validators log every session (`logIssue`, `logReceipt`) before answering, so no mix exceeds B credentials.
- **Holder authorization**: each logged session carries a signature of the root key (credential) or the
  pseudonym key (receipt) over the session hash h = H(R, e); the contract verifies it. Validators receive
  only blinded values.
- **Persistence**: issuance state lives on-chain; validators persist session nonces and answer a nonce for
  one challenge only, so a retry after a crash is safe.
- **Root-bound receipts**: receipt serial = H(root ‖ r), recomputed from the depositor at deposit; returning
  an unused credential requires a pseudonym signature. Two colluding roots can still swap receipts; the swap
  is zero-sum (see `experiments/phase5/test_foghail_cred.py`).
- Evidence: `experiments/phase5/test_foghail_cred.py` (10 adversarial tests, including a reproduction of the
  audit's counter-example on the archived v3 code) and the live-chain checks in `experiments/phase4/run_e6_v4.py`.
  Table 8 was re-measured on the v4 contract.

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
pip install numpy pandas scipy matplotlib pyarrow requests ecdsa eth-utils eth-abi eth-account psutil scikit-learn
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
5. **Credentials**: in `experiments/phase5`, `python test_foghail_cred.py` (adversarial
   protocol tests) and `python bench_v4_client.py` (client cost).
6. **On-device numbers**: build `mobile-benchmark` and press the three on-screen
   buttons (bit-level cross-check against the Python reference must pass first);
   for the 3-of-4 credential and the pseudonym-key comparison (button ⑦), see
   `experiments/e5v3_kotlin`.
7. **Chain**: follow `experiments/phase4/README.md`.

## Honest-disclosure notes

- ORide's SHE latency/bandwidth figures are the values published with SEAL
  (USENIX Sec'17); the encrypted-distance protocol itself is independently
  reconstructed with Paillier additive HE and verified exact (phase2).
- The BRIP embedding is a faithful skip-gram re-implementation of COR2Vec's
  co-occurrence objective; FastText subword features are not modeled (phase3).
- The 3-of-4 credential cost was measured on a Galaxy Tab A 8.0; the Redmi Note 8 Pro
  column of Table 7 is scaled from it by a same-device ratio (`experiments/e5v3_kotlin`).
- The Redmi client-processing figure in Table 5 predates v1.3 and used a fresh random
  key inside the timed region; the v1.3 tablet runs in `mobile-benchmark/results/` show
  that the precomputed derived key is not slower (0.95×).
- Details of each simplification are recorded in the per-directory notes.

## License and citation

Released under the MIT License (see `LICENSE`). If you use this code, please cite
the manuscript above.
