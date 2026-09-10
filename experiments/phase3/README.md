# phase3 — BRIP baseline (COR2Vec embedding matching)

Re-implements BRIP's location-embedding matching: a skip-gram embedding trained over
random walks on the OSM road network (`data/nyc_roads_major.json`, included), cosine
matching quality (Table 1, BRIP row), the geographic-distance vs embedding-similarity
non-monotonicity of Fig. 4, and the embedding-inversion attack row of Table 4.
A trained embedding `out/cor2vec.npz` is included, so training can be skipped.
Needs `../phase0`.

```
pip install numpy scipy matplotlib
python run_all.py            # train -> match -> fig4 -> inversion
python experiment_brip.py    # or run steps individually with the shipped .npz
```

FastText subword features are not modeled; see NOTES.zh.md for the full disclosure.
