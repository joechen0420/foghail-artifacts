# phase5 — ACL anonymous reputation (Python reference)

Schnorr blind-signature one-show credential on secp256r1: issue (blind-sign), show,
verify, with timings and a correctness check. Cross-checks the Kotlin build in
`../../mobile-benchmark` line by line; the paper's on-device numbers (Table 5) come
from the handset, this reference validates the logic.

```
pip install numpy ecdsa
python acl_reputation.py
```
