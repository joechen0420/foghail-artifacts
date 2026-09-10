# phase0 — Data preparation and plaintext oracle

Downloads the NYC TLC Yellow Taxi 2015-06 sample (with coordinates) from NYC Open
Data, cleans and grid-projects it, builds the driver-supply model, and computes the
plaintext top-k oracle that all matching experiments use as ground truth.
Produces the dataset statistics of paper Section 6.1.

```
pip install numpy pandas scipy pyarrow requests
python download.py     # raw data -> data/raw/
python run_all.py      # preprocess -> driver_supply -> oracle -> stats
```

Raw/derived data files are large and are rebuilt locally, not shipped.
Every other phase expects this folder to keep the name `phase0`.
