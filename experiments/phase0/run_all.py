# -*- coding: utf-8 -*-
"""一鍵串接 Phase 0：preprocess -> driver_supply -> oracle -> stats。
（download.py 另外先跑，或用 --download 一起跑）
"""
import argparse
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
STEPS = ["preprocess.py", "driver_supply.py", "oracle.py", "stats.py"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="先跑 download.py 抓樣本")
    a = ap.parse_args()
    steps = (["download.py"] if a.download else []) + STEPS
    for s in steps:
        print(f"\n===== {s} =====")
        r = subprocess.run([sys.executable, s], cwd=str(__import__("pathlib").Path(__file__).parent))
        if r.returncode != 0:
            print(f"!! {s} 失敗，中止")
            sys.exit(1)
    print("\nPhase 0 全部完成。")


if __name__ == "__main__":
    main()
