# fog-node — Standalone fog-node matcher

The same salted-Bloom-filter blind-matching core (`bloom.py`) with a console demo
(`fog_node_demo.py`) and a latency micro-benchmark (`fog_latency_bench.py`), runnable
on any PC or Raspberry Pi with the Python standard library only. Useful for
spot-checking the fog-side latency reported in Table 3 on different hardware.

```
python fog_node_demo.py
python fog_latency_bench.py
```
