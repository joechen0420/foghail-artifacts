# mobile-benchmark — On-device client benchmarks (Kotlin)

Measures on a physical Android handset (paper: Redmi Note 8 Pro, Android 9):

- **E3** client-side encoding latency, T = T_grid + T_neighbor + T_bloom + T_sign
  (Table 3, client-side column);
- **E5** ACL credential issue/show/verify timings and size (Table 5).

`FogHailBloom.kt` / `FogHailACL.kt` are the production encoding and credential
modules (BouncyCastle); `MainActivity.kt` is a three-button harness that first
cross-checks bit-level equality against the Python reference
(`reference_vectors.json`) and then runs both benchmarks on-screen.

Build: Android Studio -> New Project -> **Empty Views Activity**, package
`com.foghail.client`, minSdk 28; drop the four `.kt` files into
`app/src/main/java/com/foghail/client/`; add
`implementation 'org.bouncycastle:bcprov-jdk18on:1.78'`; run on a physical device.
Pitfalls (Android 9 EC provider, theme crash) are documented in NOTES.zh.md.
