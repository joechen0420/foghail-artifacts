# -*- coding: utf-8 -*-
"""檢查學生傳回的 v4 手機量測結果（App 按 ⑥ 複製的 JSON），並算出論文 Table 7 要填的數字。

用法：
  python experiments/e5v3_kotlin/check_phone_result.py <結果.json>

做三件事：
  1. 用 Python 參考實作重新驗證手機簽出的樣本簽章（確認手機的 Keccak／曲線運算和合約、Python 一致）；
  2. 檢查手機自報的正確性與量測次數；
  3. 印出 Table 7 的實測值，並與目前論文裡的桌機倍率推估（v4：9.5 ms、每趟 19 ms；驗證 3.3 ms）對照。
v4（2026-10-14）：另用 Python 還原手機簽出的授權簽章，確認位址與合約的 ecrecover 一致。
結果另存成同目錄 out/v4_phone_<裝置>.json。
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "phase5"))
import foghail_cred as F  # noqa: E402

ESTIMATE = {"cred_issue_3of4_v4": 9.54, "receipt_issue_3of4_v4": 9.54, "cred_verify_3of4": 3.32}


def main():
    src = Path(sys.argv[1])
    r = json.loads(src.read_text(encoding="utf-8"))
    ok = True

    s = r["sample"]
    x = int(s["x_hex"], 16)
    good = F.verify(x * F.G, bytes.fromhex(s["msg_hex"]), (bytes.fromhex(s["addrR_hex"]), int(s["s_hex"], 16)))
    print(f"1. 手機簽出的樣本，Python 重新驗證：{'通過' if good else '失敗'}")
    ok &= good

    a = r.get("auth_sample")
    good_a = False
    if a:
        from eth_account import Account
        rec = F.erecover(bytes.fromhex(a["digest_hex"]), bytes.fromhex(a["sig_hex"]))
        good_a = rec.lower()[2:] == a["addr_hex"] == Account.from_key(bytes.fromhex(a["key_hex"])).address.lower()[2:]
    print(f"1b. 手機簽出的 v4 授權簽章，Python 還原位址：{'通過' if good_a else '失敗或缺少（舊版 App？）'}")
    ok &= good_a

    print(f"2. 手機自報正確性：{r.get('correct_all_runs')}；量測次數 n={r.get('n')}，熱身 {r.get('warmup')}")
    ok &= r.get("correct_all_runs") is True and r.get("n", 0) >= 200

    print(f"\n裝置：{r.get('device')}，Android {r.get('android')}（SDK {r.get('sdk')}）\n")
    rows = [("r1 單一盲簽（舊基準）", "r1_single_issue"), ("r1 驗一次（舊基準）", "r1_single_verify"),
            ("k1 單一盲簽", "k1_single_issue"), ("k1 驗一次", "k1_single_verify"),
            ("憑證發行 3/4", "cred_issue_3of4"), ("憑證驗證 3/4", "cred_verify_3of4"),
            ("憑證出示", "cred_show"), ("收據發行 3/4", "receipt_issue_3of4"),
            ("授權簽章一次", "auth_sign_once"), ("憑證發行 v4", "cred_issue_3of4_v4"), ("收據發行 v4", "receipt_issue_3of4_v4")]
    print(f"{'項目':<16}{'p50 (ms)':>10}{'p95 (ms)':>10}{'論文目前估計':>14}")
    for label, k in rows:
        est = ESTIMATE.get(k)
        print(f"{label:<16}{r[k]['p50_ms']:>10.3f}{r[k]['p95_ms']:>10.3f}{(f'{est:.2f}' if est else ''):>14}")
    per_trip = r["cred_issue_3of4_v4"]["p50_ms"] + r["receipt_issue_3of4_v4"]["p50_ms"]
    ratio_i = r["cred_issue_3of4_v4"]["p50_ms"] / r["r1_single_issue"]["p50_ms"]
    ratio_v = r["cred_verify_3of4"]["p50_ms"] / r["r1_single_verify"]["p50_ms"]
    print(f"\n每趟合計（v4 憑證＋收據）p50 = {per_trip:.2f} ms（論文目前估計約 19 ms）")
    print(f"同一支手機上 v4/v1 倍率：發行 {ratio_i:.2f}×（桌機 4.44×）、驗證 {ratio_v:.2f}×（桌機 2.35×）")
    print(f"\n判定：{'可以用來取代論文的估計值' if ok else '不能用，請學生重跑或回報錯誤'}")

    dev = re.sub(r"[^A-Za-z0-9]+", "_", str(r.get("device", "unknown"))).strip("_")
    out = HERE / "out"; out.mkdir(exist_ok=True)
    r["_check"] = {"sample_verified_by_python": good, "auth_verified_by_python": good_a, "usable": bool(ok), "per_trip_ms": per_trip,
                   "ratio_issue_v4_over_v1": ratio_i, "ratio_verify_v3_over_v1": ratio_v}
    dst = out / f"v4_phone_{dev}.json"
    dst.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"-> {dst}")


if __name__ == "__main__":
    main()
