# -*- coding: utf-8 -*-
"""清洗 + 公尺投影 + 網格化。

輸入：data/raw/sample.parquet
輸出：data/clean/trips_grid.parquet
"""
import sys
import numpy as np
import pandas as pd
import config as C

sys.stdout.reconfigure(encoding="utf-8")


def clean(df):
    n0 = len(df)
    # 座標存在且非 0
    for lat, lon in [(C.COL_PU_LAT, C.COL_PU_LON), (C.COL_DO_LAT, C.COL_DO_LON)]:
        df = df[(df[lat].abs() > 1e-6) & (df[lon].abs() > 1e-6)]
    # 落在 bbox 內
    for lat, lon in [(C.COL_PU_LAT, C.COL_PU_LON), (C.COL_DO_LAT, C.COL_DO_LON)]:
        df = df[df[lon].between(C.LON_MIN, C.LON_MAX) & df[lat].between(C.LAT_MIN, C.LAT_MAX)]
    # 時間有效、時長合理
    dur = (df[C.COL_DO_TS] - df[C.COL_PU_TS]).dt.total_seconds()
    df = df[(dur > 0) & (dur <= C.MAX_TRIP_HOURS * 3600)]
    # 行程距離下限
    df = df[df[C.COL_DIST] >= C.MIN_MILE]
    print(f"  清洗：{n0} -> {len(df)}（保留 {len(df)/max(n0,1):.1%}）")
    return df.reset_index(drop=True)


def project_and_grid(df):
    pux, puy = C.to_meters(df[C.COL_PU_LAT].values, df[C.COL_PU_LON].values)
    dox, doy = C.to_meters(df[C.COL_DO_LAT].values, df[C.COL_DO_LON].values)
    out = pd.DataFrame({
        "pu_ts": df[C.COL_PU_TS].values,
        "do_ts": df[C.COL_DO_TS].values,
        "pu_x": pux, "pu_y": puy,
        "do_x": dox, "do_y": doy,
    })
    for g in C.GRID_SIZES:
        out[f"pu_gx_{g}"] = np.floor(pux / g).astype(np.int32)
        out[f"pu_gy_{g}"] = np.floor(puy / g).astype(np.int32)
        out[f"do_gx_{g}"] = np.floor(dox / g).astype(np.int32)
        out[f"do_gy_{g}"] = np.floor(doy / g).astype(np.int32)
    return out


def main():
    src = C.RAW / "sample.parquet"
    df = pd.read_parquet(src)
    print(f"讀入 {len(df)} 筆 <- {src}")
    df = clean(df)
    out = project_and_grid(df)
    dst = C.CLEAN / "trips_grid.parquet"
    out.to_parquet(dst, index=False)
    print(f"完成 -> {dst}")


if __name__ == "__main__":
    main()
