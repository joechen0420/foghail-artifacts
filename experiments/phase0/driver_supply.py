# -*- coding: utf-8 -*-
"""駕駛供給模型：把每個下車事件視為「一位駕駛於該時刻在該點變為可用」。

限制（論文 §6.1 須揭露）：此資料集無車輛 ID，無法串接同車連續行程，
故用「下車=供給」代理，且無法排除同車被重複計為多位可用駕駛。

輸入：data/clean/trips_grid.parquet
輸出：data/clean/driver_supply.parquet（time, x, y, 各 grid cell）
"""
import sys
import numpy as np
import pandas as pd
import config as C

sys.stdout.reconfigure(encoding="utf-8")


def build_supply(df, rho=C.RHO, seed=C.RANDOM_SEED):
    sup = pd.DataFrame({
        "time": df["do_ts"].values,
        "x": df["do_x"].values,
        "y": df["do_y"].values,
    })
    for g in C.GRID_SIZES:
        sup[f"gx_{g}"] = df[f"do_gx_{g}"].values
        sup[f"gy_{g}"] = df[f"do_gy_{g}"].values
    if rho < 1.0:
        sup = sup.sample(frac=rho, random_state=seed)
    sup = sup.sort_values("time").reset_index(drop=True)
    return sup


def main():
    df = pd.read_parquet(C.CLEAN / "trips_grid.parquet")
    sup = build_supply(df)
    dst = C.CLEAN / "driver_supply.parquet"
    sup.to_parquet(dst, index=False)
    print(f"可用駕駛事件 {len(sup)} 筆（ρ={C.RHO}）-> {dst}")


if __name__ == "__main__":
    main()
