# phase6 — Privacy attacks and ablation

Dictionary attacks (known/rotated salt), active location-harvesting query cost, and
cross-epoch pseudonym-linkage AUC (paper Table 4), plus the design ablations of
Table 7. Needs `../phase0` (data) and `../phase1/bloom.py`. Shipped results in
`out/`.

```
pip install numpy pandas scikit-learn
python attacks.py
python ablation.py
```
