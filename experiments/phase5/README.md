# phase5 — Two-sided reputation credentials

## 3-of-4 validator blind signatures (current manuscript, §4.4)

`foghail_cred.py` is the protocol reference implementation:

- four validators, each with its own issuing key; a credential on a pseudonym address
  is valid only with Schnorr blind signatures from t = 3 of them;
- each validator runs one blind session at a time (guard against the ROS attack on
  concurrent Schnorr blind signing), signs only for an open batch, at most B times per batch;
- receipts: a fresh random serial blind-signed under the validator key of its ΔR
  denomination (−2…+2), deposited later to the root identity;
- secp256k1; the challenge commits to the address of the nonce point, so the contract
  verifies a signature with one `ecrecover`.

`bench_v3_client.py` self-checks the protocol and measures client cost on a desktop
CPU, comparing the 3-of-4 secp256k1 flow against the single-session secp256r1 flow,
and scales the handset measurements by that ratio (the estimated column of Table 7).
Result: `out/v3_client_bench.json`.

```
pip install numpy ecdsa eth-utils
python bench_v3_client.py
```

## v1.0 single-issuer reference

`acl_reputation.py`: single-issuer Schnorr blind-signature one-show credential on
secp256r1 (issue, show, verify). It cross-checks the Kotlin build in
`../../mobile-benchmark`, whose handset numbers form the measured column of Table 7.

```
python acl_reputation.py
```
