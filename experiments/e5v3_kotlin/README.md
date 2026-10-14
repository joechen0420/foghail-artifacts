# e5v3_kotlin — 3-of-4 credential on the handset

Kotlin port of the 3-of-4 validator blind-signature credential and of the v4 authorization
signature (Ethereum personal_sign, secp256k1 ECDSA, RFC 6979, low-s), for measuring their cost
on a physical Android handset. Table 7 currently reports this cost as an estimate
scaled from a desktop ratio; this harness replaces the estimate with a measurement.

| File | Contents |
|---|---|
| `FogHailCredV3.kt` | secp256k1 Schnorr blind signatures with the challenge bound to the nonce-point address (Keccak-256), ROS guard, timing functions; matches `../phase5/foghail_cred.py` |
| `MainActivity.kt` | Measurement app: buttons ①–③ as in `mobile-benchmark`; ④ v3 cross-check, ⑤ v3 timing, ⑥ copy result JSON |
| `V3VectorTest.kt` | JVM unit tests: Python reference vectors, known address of private key 1, byte-exact v4 authorization signature, blind-signature self-check, ROS guard, timing smoke test |
| `reference_vectors_v3.json` | Reference vectors produced by the Python implementation |
| `app_build.gradle.kts`, `AndroidManifest.xml` | App module settings (AGP 9.2.1, BouncyCastle 1.79, minSdk 26, package `com.foghail.client`) |
| `check_phone_result.py` | Re-verifies the blind signature and the authorization signature produced on the phone in Python and prints the Table 7 figures |

```
python check_phone_result.py <result.json>
```

Extended notes in Chinese: `NOTES.zh.md`.
