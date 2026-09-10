# phase2 — ORide baseline

Reconstructs the ORide encrypted-distance protocol with Paillier additive HE,
verifies that its matching quality equals the plaintext oracle (Table 1, ORide row),
and reports the published SEAL cost figures for comparison (Table 3). Needs
`../phase0` (config + data) and `../phase1/bloom.py`.

```
pip install numpy pandas scipy
python oride_ref.py
```
