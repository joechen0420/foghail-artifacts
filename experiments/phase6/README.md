# phase6 — Privacy attacks, anonymity set, and ablation

Dictionary attacks (known/rotated salt), active location-harvesting query cost, and
cross-epoch bit-pattern linkage AUC (paper Table 6), plus the design ablations of
Table 9. Needs `../phase0` (data) and `../phase1/bloom.py`. Shipped results in `out/`.

`anonymity_set.py` measures the anonymity set k left to an adversary that knows every
epoch salt and decodes each upload to its cell: riders per cell per 1 h epoch, drivers
per cell per 30 s window, at 100 m and 250 m grids (last two rows of Table 6).
Result: `out/anonymity_set.json`.

```
pip install numpy pandas scikit-learn
python attacks.py
python ablation.py
python anonymity_set.py
```
