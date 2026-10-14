# phase5 — Two-sided reputation credentials

## v4 protocol (current manuscript, §4.4)

`foghail_cred.py` is the protocol reference implementation:

- four validators, each with its own issuing key; a credential on a pseudonym address is valid only
  with Schnorr blind signatures from t = 3 of them (secp256k1, challenge bound to the nonce-point
  address, so the contract verifies one signature with one `ecrecover`);
- two-phase validator interface `cred_commit(root) -> (sid, R)`, `cred_respond(sid, e, auth) -> s`
  (receipts alike): validators see only blinded challenges and the holder's authorization signature;
- every partial signature is logged on-chain against a batch budget of 3B before it is released;
- one open blind session per key (ROS guard); nonces persisted before R is released, and a nonce is
  answered for one challenge only;
- receipt serial H(root ‖ r); `LocalLedger` mirrors the contract rules for offline tests.

```
pip install numpy ecdsa eth-utils eth-abi eth-account psutil
python test_foghail_cred.py     # 10 adversarial tests -> out/v4_protocol_tests.json
python bench_v4_client.py       # client cost, pinned to one core -> out/v4_client_bench.json
```

## Earlier versions

- `foghail_cred_v3.py`, `bench_v3_client.py`: v3 (per-validator quota), kept to reproduce the audit's
  counter-example and the earlier numbers.
- `acl_reputation.py`: v1.0 single-issuer secp256r1 credential; cross-checks the Kotlin build in
  `../../mobile-benchmark`, whose handset numbers form the measured column of Table 7.
