# -*- coding: utf-8 -*-
"""v3 憑證協定的客戶端成本（桌機量測，2026-10-14）。

論文 Table 7 的手機數字（Redmi Note 8 Pro）量的是 v1：單一發行者、secp256r1 Schnorr 盲簽章。
v3 改成 secp256k1（合約可用 ecrecover 驗）＋ 3/4 門檻（每張憑證 3 次盲簽、驗 3 次），
另外每趟多一張收據（同樣 3 次盲簽）。手機目前無法重量，所以在同一台桌機、同一個 Python ecdsa
函式庫上量兩種作法，取「v3 / v1」倍率，再乘上手機的 v1 實測值得到手機估計值。論文中標為估計值。

輸出：out/v3_client_bench.json
"""
import sys
import json
import time
import hashlib
from pathlib import Path
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import acl_reputation as V1      # noqa: E402  secp256r1 單一發行者
import foghail_cred as F         # noqa: E402  secp256k1 v3

REPS = 300
PHONE_V1 = {"issue_ms": 2.15, "verify_ms": 1.41}   # Table 7（乘客）


def timeit(fn, reps=REPS):
    ts = []
    for _ in range(reps):
        t = time.perf_counter(); fn(); ts.append((time.perf_counter() - t) * 1000)
    return float(np.median(ts))


def main():
    iss1 = V1.Issuer()
    msg = hashlib.sha256(b"m").digest()
    cred1 = V1.blind_issue(iss1, msg)
    v1_issue = timeit(lambda: V1.blind_issue(iss1, msg))
    v1_verify = timeit(lambda: V1.verify(iss1.PK, msg, cred1))

    vals = [F.Issuer() for _ in range(3)]
    m = b"\x11" * 20
    sigs = [F.blind_sign(v, m) for v in vals]
    k1_one_issue = timeit(lambda: F.blind_sign(vals[0], m))
    k1_one_verify = timeit(lambda: F.verify(vals[0].P, m, sigs[0]))
    v3_issue = timeit(lambda: [F.blind_sign(v, m) for v in vals])
    v3_verify = timeit(lambda: [F.verify(v.P, m, s) for v, s in zip(vals, sigs)])

    r_issue = v3_issue / v1_issue
    r_verify = v3_verify / v1_verify
    out = {
        "desktop_ms": {"v1_r1_single_issue": v1_issue, "v1_r1_single_verify": v1_verify,
                       "k1_single_issue": k1_one_issue, "k1_single_verify": k1_one_verify,
                       "v3_k1_3of4_issue": v3_issue, "v3_k1_3of4_verify": v3_verify},
        "ratio_v3_over_v1": {"issue": r_issue, "verify": r_verify},
        "phone_v1_measured_ms": PHONE_V1,
        "phone_v3_estimated_ms": {
            "credential_issue": PHONE_V1["issue_ms"] * r_issue,
            "credential_verify": PHONE_V1["verify_ms"] * r_verify,
            "receipt_issue": PHONE_V1["issue_ms"] * r_issue,
            "per_trip_total": PHONE_V1["issue_ms"] * r_issue * 2,   # 憑證＋收據；驗證由合約做
        },
    }
    for k, v in out["desktop_ms"].items():
        print(f"  {k:>24}: {v:.2f} ms")
    print(f"  倍率 v3/v1：發行 {r_issue:.2f}×、驗證 {r_verify:.2f}×")
    for k, v in out["phone_v3_estimated_ms"].items():
        print(f"  手機估計 {k}: {v:.2f} ms")
    (HERE / "out").mkdir(exist_ok=True)
    json.dump(out, open(HERE / "out" / "v3_client_bench.json", "w", encoding="utf-8"), indent=2)


if __name__ == "__main__":
    main()
