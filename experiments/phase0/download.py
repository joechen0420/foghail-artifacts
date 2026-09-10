# -*- coding: utf-8 -*-
"""從 NYC Open Data（Socrata API）分頁下載 2015 Yellow Taxi 樣本。

用法：
    python download.py                      # 抓 config 預設樣本範圍
    python download.py --start 2015-06-01T00:00:00 --end 2015-06-02T00:00:00
    python download.py --max-rows 200000    # 上限（避免整月過慢）
"""
import argparse
import time
import urllib.parse
import urllib.request
import json
import sys
import pandas as pd
import config as C

sys.stdout.reconfigure(encoding="utf-8")

FIELDS = [
    C.COL_PU_TS, C.COL_DO_TS, C.COL_PU_LAT, C.COL_PU_LON,
    C.COL_DO_LAT, C.COL_DO_LON, C.COL_DIST,
]


def fetch(start, end, max_rows):
    where = f"{C.COL_PU_TS} between '{start}' and '{end}'"
    select = ",".join(FIELDS)
    rows, offset = [], 0
    while True:
        params = {
            "$select": select,
            "$where": where,
            "$order": C.COL_PU_TS,     # 穩定分頁需 order
            "$limit": C.PAGE_SIZE,
            "$offset": offset,
        }
        url = C.SOCRATA_URL + "?" + urllib.parse.urlencode(params)
        for attempt in range(4):
            try:
                with urllib.request.urlopen(url, timeout=120) as r:
                    page = json.load(r)
                break
            except Exception as e:
                print(f"  retry {attempt+1}: {e}")
                time.sleep(5)
        else:
            raise RuntimeError("下載失敗，請稍後重試或縮小範圍")
        if not page:
            break
        rows.extend(page)
        print(f"  已抓 {len(rows)} 筆 (offset={offset})")
        offset += C.PAGE_SIZE
        if len(page) < C.PAGE_SIZE or (max_rows and len(rows) >= max_rows):
            break
    return rows[:max_rows] if max_rows else rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=C.SAMPLE_START)
    ap.add_argument("--end", default=C.SAMPLE_END)
    ap.add_argument("--max-rows", type=int, default=None)
    ap.add_argument("--out", default=str(C.RAW / "sample.parquet"))
    a = ap.parse_args()

    print(f"下載 {a.start} ~ {a.end} …")
    rows = fetch(a.start, a.end, a.max_rows)
    df = pd.DataFrame(rows)
    for c in (C.COL_PU_LAT, C.COL_PU_LON, C.COL_DO_LAT, C.COL_DO_LON, C.COL_DIST):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in (C.COL_PU_TS, C.COL_DO_TS):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df.to_parquet(a.out, index=False)
    print(f"完成：{len(df)} 筆 -> {a.out}")


if __name__ == "__main__":
    main()
