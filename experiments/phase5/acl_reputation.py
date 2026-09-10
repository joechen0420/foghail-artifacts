# -*- coding: utf-8 -*-
"""Phase 5：雙邊不可連結信譽（ACL 一次性憑證）參考實作與 E5 開銷量測。

實作 ACL 精神的核心：以 secp256r1 上的 Schnorr 盲簽章做「一次性憑證」——
發行方（鏈上多簽合約代表）對使用者的假名盲簽，證明其信譽 R≥θ 而不知其身分；
使用者出示時揭露 (訊息, 簽章) 供驗證，且發行與出示不可連結（盲因子隨機）。

量測（E5，供表 5）：憑證取得（盲簽一輪）/出示/驗證的時間與大小，乘客與駕駛分列
（駕駛每班次一張、乘客每行程一張）。

註：ACL（Baldimtsi-Lysyanskaya, CCS'13）原用受限盲簽章；此處以 Schnorr 盲簽章
作等價開銷量測（同為單一 EC 群、無 pairing、行動端可行——PrivateRide 亦走此路線）。
環境：純 Python ecdsa 群運算（伺服器 CPU）；實體手機/NDK 會更快，如 PrivateRide 所示。
"""
import sys
import time
import hashlib
import secrets
import numpy as np
from ecdsa import NIST256p
from ecdsa.ellipticcurve import INFINITY

sys.stdout.reconfigure(encoding="utf-8")

CURVE = NIST256p
G = CURVE.generator
N = CURVE.order


def _H(*pts_and_msg):
    h = hashlib.sha256()
    for x in pts_and_msg:
        if isinstance(x, bytes):
            h.update(x)
        else:  # EC point
            h.update(int(x.x()).to_bytes(32, "big"))
            h.update(int(x.y()).to_bytes(32, "big"))
    return int.from_bytes(h.digest(), "big") % N


class Issuer:
    """發行方（鏈上多簽合約代表）：持有簽發私鑰。"""
    def __init__(self):
        self.sk = secrets.randbelow(N - 1) + 1
        self.PK = self.sk * G

    def sign_commit(self):
        k = secrets.randbelow(N - 1) + 1
        return k, k * G       # 回傳承諾 R=kG（k 私存）

    def sign_response(self, k, e):
        return (k + e * self.sk) % N   # s = k + e·x


def blind_issue(issuer, msg):
    """盲簽章一輪：使用者對 msg（假名+信譽承諾）取得可驗證簽章，
    發行方不知 msg 內容（盲化）。回傳 (e, s) 與量測用時間。"""
    # 1. 發行方承諾
    k, Rc = issuer.sign_commit()
    # 2. 使用者盲化：選盲因子 a,b，算 R' = R + aG + b·PK，挑戰 e' = H(R', msg)，送 e = e'−b
    a = secrets.randbelow(N - 1) + 1
    b = secrets.randbelow(N - 1) + 1
    Rp = Rc + a * G + b * issuer.PK
    e_prime = _H(Rp, msg)
    e = (e_prime + b) % N       # 去盲後 Rv=s'G−e'PK 才會等於 R'
    # 3. 發行方回應
    s = issuer.sign_response(k, e)
    # 4. 使用者去盲：s' = s + a
    s_prime = (s + a) % N
    return (e_prime, s_prime, Rp)


def verify(issuer_PK, msg, cred):
    """驗證一次性憑證：檢查 e' == H(s'G − e'·PK, msg)。"""
    e_prime, s_prime, _ = cred
    Rv = s_prime * G + (N - e_prime) * issuer_PK  # s'G − e'·PK
    return _H(Rv, msg) == e_prime


def bench(role, n_trips, seed=0):
    """量測某一方（乘客/駕駛）n 次憑證操作的平均時間。"""
    rng = np.random.default_rng(seed)
    issuer = Issuer()
    t_issue = t_show = t_verify = 0.0
    ok = 0
    sizes = []
    for i in range(n_trips):
        # 每行程/班次的假名訊息（信譽承諾雜湊）
        msg = hashlib.sha256(f"{role}-pseudo-{i}-R>=theta".encode()).digest()
        t = time.perf_counter()
        cred = blind_issue(issuer, msg)
        t_issue += time.perf_counter() - t
        # 出示 = 傳 (msg, e', s')；大小 = 32(msg)+32+32
        t = time.perf_counter()
        payload = msg + int(cred[0]).to_bytes(32, "big") + int(cred[1]).to_bytes(32, "big")
        t_show += time.perf_counter() - t
        sizes.append(len(payload))
        t = time.perf_counter()
        ok += verify(issuer.PK, msg, cred)
        t_verify += time.perf_counter() - t
    return {
        "role": role, "trips": n_trips,
        "issue_ms": t_issue * 1000 / n_trips,
        "show_ms": t_show * 1000 / n_trips,
        "verify_ms": t_verify * 1000 / n_trips,
        "cred_bytes": int(np.mean(sizes)),
        "verified_ok": ok == n_trips,
    }


def main():
    import json
    from pathlib import Path
    OUT = Path(__file__).resolve().parent / "out"; OUT.mkdir(exist_ok=True)
    print("ACL 一次性憑證開銷（secp256r1，純 Python ecdsa；伺服器 CPU）")
    rider = bench("rider", 300, seed=1)
    driver = bench("driver", 300, seed=2)
    for r in (rider, driver):
        print(f"  {r['role']:>6}: 取得 {r['issue_ms']:.2f}ms  出示 {r['show_ms']:.3f}ms  "
              f"驗證 {r['verify_ms']:.2f}ms  憑證 {r['cred_bytes']}B  正確={r['verified_ok']}")
    print("\n  [對照] PrivateRide 發表值（LG G3, EC-224）：取得 AC 554 ms、出示 219 ms、盲簽 68 ms")
    json.dump({"rider": rider, "driver": driver},
              open(OUT / "phase5_results.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\n-> {OUT/'phase5_results.json'}")


if __name__ == "__main__":
    main()
