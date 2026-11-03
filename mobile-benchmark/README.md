# mobile-benchmark — On-device client benchmarks (Kotlin)

Measures on a physical Android handset (paper: Redmi Note 8 Pro, Android 9):

- **E3** client-side encoding latency, T = T_grid + T_neighbor + T_bloom + T_sign
  (Table 5, client-processing row);
- **E5** single-session credential issue/show/verify timings and size (Table 7,
  single-session column).

Since v1.3, `FogHailBloom.derivePseudonym` derives the request-signing key as
SHA-256(root ‖ t) mod n on secp256r1, and `E3LatencyBench.run` takes a `keyMode`:
`"random"` (v1.2 behaviour, fresh key inside the timed region), `"derived"`
(derivation inside the timed region), or `"precomputed"` (derivation before the
timer, reported separately as `T_derive`). The three-mode comparison is driven by
button ⑦ of the app in `../experiments/e5v3_kotlin`. Raw results from two runs on a
Galaxy Tab A 8.0 (SM-T295) are in `results/` (`e3_v5_*`: random vs. derived;
`e3_v6_*`: all three modes); `python check_e3_result.py results/e3_v6_*.json`
summarizes them (§6.3).

`FogHailBloom.kt` / `FogHailACL.kt` are the production encoding and credential
modules (BouncyCastle); `MainActivity.kt` is a three-button harness that first
cross-checks bit-level equality against the Python reference
(`reference_vectors.json`) and then runs both benchmarks on-screen.

Build: Android Studio -> New Project -> **Empty Views Activity**, package
`com.foghail.client`, minSdk 28; drop the four `.kt` files into
`app/src/main/java/com/foghail/client/`; add
`implementation 'org.bouncycastle:bcprov-jdk18on:1.78'`; run on a physical device.
Pitfalls (Android 9 EC provider, theme crash) are documented in NOTES.zh.md.
