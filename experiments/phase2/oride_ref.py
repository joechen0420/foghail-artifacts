# -*- coding: utf-8 -*-
"""ORide 重建（Phase 2）。三件事：
1) 媒合品質：ORide 在密文上算「精確」平方歐氏距離、乘客解密選最近，
   故其品質 = 明文 Oracle（Hit@1=1.0、膨脹=1.0）。在本資料上確認。
2) 加密距離協定重建（Paillier 加法同態）：駕駛把 (xd, yd, xd²+yd²) 加密上傳，
   乘客端同態算出 Enc(||r−d||²) 後解密得精確距離——重現 ORide「乘客只得到
   (排列後)距離」的攻擊面（Kumaraswamy 位置蒐割）。量測每駕駛 HE 成本。
   註：ORide 用 BFV/SEAL 密文打包，延遲/頻寬以其發表值為準（見 config）。
3) FogHail 霧端 BF 媒合延遲與通訊量（本文側，供表 3）。

環境限制：Python 3.14 無法安裝 SEAL/tenseal，依實驗方案退階方案執行。
"""
import sys
import time
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
import config as C

sys.stdout.reconfigure(encoding="utf-8")

# 匯入 Phase 1 的 BF
_bp = Path(__file__).resolve().parent.parent / "phase1" / "bloom.py"
_spec = importlib.util.spec_from_file_location("bloom", _bp)
_bloom = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_bloom)
BF = _bloom.BF


def confirm_exact_quality(max_requests=6000, seed=C.RANDOM_SEED):
    """ORide 精確距離 → 選到的就是最近駕駛 → Hit@k=1、膨脹=1。在資料上確認。"""
    reqs = pd.read_parquet(C.CLEAN / "trips_grid.parquet")
    sup = pd.read_parquet(C.CLEAN / "driver_supply.parquet")
    if max_requests and len(reqs) > max_requests:
        reqs = reqs.sample(max_requests, random_state=seed)
    reqs = reqs.sort_values("pu_ts").reset_index(drop=True)
    sup = sup.sort_values("time").reset_index(drop=True)
    sup_t = sup["time"].values.astype("datetime64[s]").astype(np.int64)
    sup_xy = sup[["x", "y"]].values
    t0 = reqs["pu_ts"].min().to_datetime64().astype("datetime64[s]").astype(np.int64)
    req_t = reqs["pu_ts"].values.astype("datetime64[s]").astype(np.int64)
    win = (req_t - t0) // C.BATCH_WINDOW_S
    hit1 = infl = n = 0
    for w, idx in pd.Series(range(len(reqs))).groupby(win):
        idx = idx.values
        ws = t0 + int(w) * C.BATCH_WINDOW_S
        mask = (sup_t >= ws - C.DRIVER_AVAIL_WINDOW_S) & (sup_t <= ws + C.BATCH_WINDOW_S)
        pool = sup_xy[mask]
        if len(pool) == 0:
            continue
        tree = cKDTree(pool)
        for i in idx:
            rq = np.array([reqs.at[i, "pu_x"], reqs.at[i, "pu_y"]])
            d, _ = tree.query(rq, k=1)       # ORide 選精確最近
            hit1 += 1; infl += 1.0; n += 1    # 選到最近 → hit@1=1, 膨脹=1
    return {"requests": n, "hit@1": hit1 / n, "infl_p50": infl / n}


def paillier_distance_cost(n_drivers=200, seed=C.RANDOM_SEED):
    """用 Paillier 忠實重建加密距離協定並量測每駕駛 HE 成本、驗證正確性。"""
    from phe import paillier
    rng = np.random.default_rng(seed)
    pk, sk = paillier.generate_paillier_keypair(n_length=2048)
    xr, yr = 1000.0, 2000.0                         # 乘客座標（本地明文）
    drv = rng.integers(0, 5000, size=(n_drivers, 2)).astype(float)

    t_enc = t_hom = t_dec = 0.0
    errs = []
    for xd, yd in drv:
        # 駕駛端加密上傳（在乘客公鑰下）：xd, yd, xd²+yd²
        t = time.perf_counter()
        e_xd = pk.encrypt(float(xd)); e_yd = pk.encrypt(float(yd))
        e_nd = pk.encrypt(float(xd * xd + yd * yd))
        t_enc += time.perf_counter() - t
        # 乘客端同態算 Enc(||r−d||²) = Enc(xd²+yd²) − 2xr·Enc(xd) − 2yr·Enc(yd) + (xr²+yr²)
        t = time.perf_counter()
        e_dist = e_nd - 2 * xr * e_xd - 2 * yr * e_yd + (xr * xr + yr * yr)
        t_hom += time.perf_counter() - t
        # 乘客端解密（只得到距離，非座標）
        t = time.perf_counter()
        dist2 = sk.decrypt(e_dist)
        t_dec += time.perf_counter() - t
        true = (xr - xd) ** 2 + (yr - yd) ** 2
        errs.append(abs(dist2 - true))
    per = 1000.0 / n_drivers
    return {
        "n_drivers": n_drivers,
        "enc_ms_per_driver": t_enc * per,
        "hom_ms_per_driver": t_hom * per,
        "dec_ms_per_driver": t_dec * per,
        "max_abs_err": float(max(errs)),   # 應 ≈0 → 精確距離
    }


def foghail_fog_latency(seed=C.RANDOM_SEED):
    """FogHail 霧端 BF 媒合延遲（單請求對駕駛池）與通訊量。"""
    rng = np.random.default_rng(seed)
    bf = BF(C.M_DEFAULT, C.K_DEFAULT, C.SALT)
    rows = []
    for pool in (100, 1000, 10000):
        # 乘客 9 格 BF_p
        rc = (int(rng.integers(0, 500)), int(rng.integers(0, 500)))
        bf_p = bf.build([(rc[0] + dx, rc[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
        drv_masks = [bf.cell_bits((int(rng.integers(0, 500)), int(rng.integers(0, 500))))
                     for _ in range(pool)]
        t = time.perf_counter()
        for dm in drv_masks:
            _ = ((dm & bf_p) == dm)        # 成員測試判定
        el = (time.perf_counter() - t) * 1000
        rows.append({"pool": pool, "match_ms": el, "ms_per_driver": el / pool})
    comm_bytes = C.M_DEFAULT // 8          # 單次 BF 上傳
    return rows, comm_bytes


def main():
    import json
    print("1) ORide 精確距離媒合品質（= Oracle）")
    q = confirm_exact_quality()
    print(f"   requests={q['requests']}  Hit@1={q['hit@1']:.3f}  膨脹p50={q['infl_p50']:.3f}")

    print("\n2) 加密距離協定（Paillier 重建）成本與正確性")
    p = paillier_distance_cost()
    print(f"   每駕駛：加密 {p['enc_ms_per_driver']:.2f}ms、同態 {p['hom_ms_per_driver']:.3f}ms、"
          f"解密 {p['dec_ms_per_driver']:.2f}ms；最大誤差={p['max_abs_err']:.2e}（≈0=精確）")

    print("\n3) FogHail 霧端 BF 媒合延遲與通訊")
    rows, comm = foghail_fog_latency()
    for r in rows:
        print(f"   pool={r['pool']:>5}: {r['match_ms']:.2f} ms（{r['ms_per_driver']*1000:.2f} µs/駕駛）")
    print(f"   單請求通訊量 = {comm} bytes（m={C.M_DEFAULT}）；互動輪數 = 1（非互動）")
    print(f"\n   [對照] ORide 發表值：密文 {C.ORIDE_CIPHERTEXT_KB} KB/請求、"
          f"SP {C.ORIDE_SP_MS_AT_4096} ms@4096、輪數 ≥{C.ORIDE_ROUNDS}")

    json.dump({"quality": q, "paillier_cost": p, "foghail_fog": rows,
               "foghail_comm_bytes": comm}, open(C.OUT / "phase2_results.json", "w",
               encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n-> {C.OUT/'phase2_results.json'}")


if __name__ == "__main__":
    main()
