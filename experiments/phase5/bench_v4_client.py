# -*- coding: utf-8 -*-
"""v4 憑證協定的客戶端成本（桌機量測，2026-10-14）。

v4 比 v3 多一件事：每個部分簽章的申請都要附一個授權簽章（憑證由根私鑰簽、收據由假名私鑰簽，
secp256k1 ECDSA）。所以每張憑證＝3 ×（一次盲簽會談＋一次授權簽章），收據相同。
方法同 bench_v3_client.py：同一台桌機、同一個 Python ecdsa 函式庫量 v1（單一發行者、secp256r1）與 v4，
取倍率乘上手機的 v1 實測值，得到手機估計值（論文 Table 7 標為估計）。

輸出：out/v4_client_bench.json
"""
import sys
import json
import time
import hashlib
from pathlib import Path
import numpy as np
from ecdsa import SigningKey, SECP256k1

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import acl_reputation as V1      # noqa: E402  secp256r1 單一發行者
import foghail_cred as F         # noqa: E402  secp256k1 v4

REPS = 300
PHONE_V1 = {"issue_ms": 2.15, "verify_ms": 1.41}   # Table 7（乘客）


def timeit(fn, reps=REPS):
    ts = []
    for _ in range(reps):
        t = time.perf_counter(); fn(); ts.append((time.perf_counter() - t) * 1000)
    return float(np.median(ts))


def pin_one_core(core=2):
    """混合架構 CPU（效能核心＋節能核心）上，行程在核心間遷移會讓量測差到兩倍；綁一顆效能核心。"""
    try:
        import psutil
        psutil.Process().cpu_affinity([core])
        return core
    except Exception:
        return None


def main():
    core = pin_one_core()
    iss1 = V1.Issuer()
    msg = hashlib.sha256(b"m").digest()
    v1_issue = timeit(lambda: V1.blind_issue(iss1, msg))

    vals = [F.Issuer() for _ in range(3)]
    sk = SigningKey.generate(curve=SECP256k1)
    digest = hashlib.sha256(b"auth").digest()
    m = b"\x11" * 20
    blind_one = timeit(lambda: F.blind_sign(vals[0], m))
    auth_one = timeit(lambda: sk.sign_digest(digest))
    v3_issue = timeit(lambda: [F.blind_sign(v, m) for v in vals])
    v4_issue = timeit(lambda: [(F.blind_sign(v, m), sk.sign_digest(digest)) for v in vals])

    r3, r4 = v3_issue / v1_issue, v4_issue / v1_issue
    cred3, cred4 = PHONE_V1["issue_ms"] * r3, PHONE_V1["issue_ms"] * r4
    out = {
        "desktop_ms": {"v1_r1_single_issue": v1_issue, "k1_blind_session": blind_one,
                       "k1_auth_signature": auth_one, "v3_3of4_issue": v3_issue, "v4_3of4_issue_with_auth": v4_issue},
        "ratio_over_v1": {"v3": r3, "v4": r4},
        "pinned_core": core,
        "phone_v1_measured_ms": PHONE_V1,
        "phone_estimated_ms": {
            "v3_credential_issue": cred3, "v3_per_trip": 2 * cred3,
            "v4_credential_issue": cred4, "v4_receipt_issue": cred4, "v4_per_trip": 2 * cred4,
        },
    }
    for k, v in out["desktop_ms"].items():
        print(f"  {k:>26}: {v:.2f} ms")
    print(f"  倍率（對 v1）：v3 {r3:.2f}×、v4 {r4:.2f}×")
    for k, v in out["phone_estimated_ms"].items():
        print(f"  手機估計 {k}: {v:.2f} ms")
    (HERE / "out").mkdir(exist_ok=True)
    json.dump(out, open(HERE / "out" / "v4_client_bench.json", "w", encoding="utf-8"), indent=2)


if __name__ == "__main__":
    main()
