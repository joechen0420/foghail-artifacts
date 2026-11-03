# -*- coding: utf-8 -*-
"""檢查學生傳回的 ⑦ E3 新舊對照結果，並換算 Redmi Note 8 Pro 的數字。

用法：python experiments/e3_kotlin/check_e3_result.py 結果1.json [結果2.json ...]
（把學生貼回的 JSON 存成檔案；兩次量測就給兩個檔）

換算方式與 Table 7 相同：Redmi 新值 = Redmi 舊實測值 × 平板同機倍率（新/舊）。
Redmi 舊實測值是論文 8 月的 E3：p50 0.70 ms、p95 1.65 ms（舊程式＝隨機金鑰）。

v5（10-30）只有 random／derived 兩種、6 輪；v6（11-03）多了 precomputed
（推導在閒置時先算好、不計入請求延遲），9 輪。v6 的結果另外換算「預先推導」，
論文 Table 5 用的是這一組；推導本身的時間（derive_p50/p95）照平板實測值另列。
"""
import json
import statistics
import sys

REDMI_OLD = {"p50": 0.70, "p95": 1.65}

if len(sys.argv) < 2:
    sys.exit(__doc__)


def report(label, key50, key95, good):
    rs50 = [g["summary"][key50] for g in good]
    rs95 = [g["summary"][key95] for g in good]
    if len(rs50) >= 2:
        spread = (max(rs50) - min(rs50)) / statistics.mean(rs50)
        print(f"\n[{label}] 兩次倍率相差 {spread:.1%}（< 10% 算穩定）")
    r50, r95 = statistics.mean(rs50), statistics.mean(rs95)
    print(f"[{label}] Redmi 換算：p50 {REDMI_OLD['p50']} × {r50:.2f} = {REDMI_OLD['p50'] * r50:.2f} ms；"
          f"p95 {REDMI_OLD['p95']} × {r95:.2f} = {REDMI_OLD['p95'] * r95:.2f} ms")


good, rows = [], []
for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as f:
        j = json.load(f)
    s = j["summary"]
    v6 = "precomputed_total_p50_ms" in s
    problems = []
    if not j.get("derive_check_pass"):
        problems.append("推導對拍未通過")
    if "sdk_gphone" in j.get("device", "") or "Emulator" in j.get("device", ""):
        problems.append("看起來是模擬器")
    want = 9 if v6 else 6
    if len(j.get("rounds", [])) != want:
        problems.append(f"輪數 {len(j.get('rounds', []))} ≠ {want}")
    rows.append((path, j, problems))
    if not problems:
        good.append(j)

for path, j, problems in rows:
    s = j["summary"]
    print(f"{path}  [{j['device']}, Android {j['android']}, {j.get('app')}]  "
          f"{'✓' if not problems else '✗ ' + '、'.join(problems)}")
    print(f"  舊       p50 {s['random_total_p50_ms']:.3f} / p95 {s['random_total_p95_ms']:.3f} ms")
    print(f"  推導     p50 {s['derived_total_p50_ms']:.3f} / p95 {s['derived_total_p95_ms']:.3f} ms"
          f"（倍率 {s['ratio_p50']:.2f} / {s['ratio_p95']:.2f}）")
    if "precomputed_total_p50_ms" in s:
        print(f"  預先推導 p50 {s['precomputed_total_p50_ms']:.3f} / p95 {s['precomputed_total_p95_ms']:.3f} ms"
              f"（倍率 {s['pre_ratio_p50']:.2f} / {s['pre_ratio_p95']:.2f}）")
        print(f"  推導本身 p50 {s['derive_p50_ms']:.3f} / p95 {s['derive_p95_ms']:.3f} ms（平板實測，閒置時）")

if good:
    report("推導在計時內", "ratio_p50", "ratio_p95", good)
    v6s = [g for g in good if "precomputed_total_p50_ms" in g["summary"]]
    if v6s:
        report("預先推導", "pre_ratio_p50", "pre_ratio_p95", v6s)
        print(f"[推導本身] 平板 p50 {statistics.mean(g['summary']['derive_p50_ms'] for g in v6s):.2f} ms；"
              f"p95 {statistics.mean(g['summary']['derive_p95_ms'] for g in v6s):.2f} ms")
    print("→ 論文要改的位置：Table 5（Client processing 列）、§6 Redmi 編碼＋簽章那句、§8 結論 0.70 ms、§5 補預先推導")
