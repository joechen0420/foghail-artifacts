# phase1 — Blind matching (FogHail core)

Fog-node blind proximity matching over salted Bloom filters: matching quality vs the
plaintext oracle, fog-side latency/bandwidth, false-positive-rate sweeps, and the
grid-granularity trade-off. Reproduces the FogHail rows of paper Tables 1-3 and
Figs. 2-3. Requires phase0 ground truth (run phase0 first); `out/` already contains
the CSV/JSON used in the paper, so `python plots.py` regenerates the figures without
re-running anything.

```
pip install numpy pandas scipy matplotlib ecdsa
python run_all.py            # E2 quality + FPR sweep -> out/
python plots.py              # Figs. 2-3 (LANG_EN=1 for English labels)
```
