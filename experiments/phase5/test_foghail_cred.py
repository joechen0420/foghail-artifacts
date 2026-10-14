# -*- coding: utf-8 -*-
"""v4 憑證協定的對抗測試（對應 外審回稿/Code_Audit_2026-10-14.md 的 P0-1、P0-2、P0-3、P1）。

不必開鏈：用 foghail_cred.LocalLedger（合約規則的 Python 鏡像）。活鏈上的同一組關鍵測試在
../phase4/run_e6_v4.py。

    python test_foghail_cred.py        # 逐項印結果，存 out/v4_protocol_tests.json
    python -m pytest test_foghail_cred.py
"""
import json
import random
import secrets
import sys
import tempfile
from pathlib import Path

from eth_account import Account

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import foghail_cred as F  # noqa: E402


def setup(theta=0, store_dir=None):
    L = F.LocalLedger(theta)
    vals = [F.Validator(i, L, store_path=(Path(store_dir) / f"v{i}.json") if store_dir else None)
            for i in range(4)]
    L.add_validators(vals)
    return L, vals


def root(L):
    a = Account.create()
    L.register_root(a.address)
    return a


def m_of(p):
    return bytes.fromhex(p.address[2:])


def refused(fn):
    try:
        fn()
    except (PermissionError, RuntimeError) as e:
        return str(e)
    return None


def cred(L, vals, idxs, owner, p=None):
    p = p or Account.create()
    return p, F.obtain_credential([vals[i] for i in idxs], L, owner, m_of(p))


def trip(L, rp, rc, rg, dp, dc, dg, status=0):
    L.settle(secrets.token_bytes(32), (rp.address, rg, rc), (dp.address, dg, dc), status)


# ------------------------------------------------------------------ P0-1
def test_p01_v3_reproduces_audit():
    """對照組：用封存的 v3 程式重現稽核反例（B=3 湊出 4 張），證明問題在修正前確實存在。"""
    import foghail_cred_v3 as F3

    class Chain:
        def theta(self):
            return 0

        def root_rep(self, r):
            return 0

        def batch(self, r):
            return 1, 3
    vals = [F3.Validator(i) for i in range(4)]
    got = 0
    for k, s in enumerate([(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)]):
        m = bytes([k + 1]) * 20
        sigs = [vals[i].issue_credential(Chain(), b"root", m, F3.blind_sign) for i in s]
        got += all(F3.verify(vals[i].cred.P, m, g) for i, g in zip(s, sigs))
    counts = [vals[i].signed_batch[(b"root", 1)] for i in range(4)]
    assert got == 4 and counts == [3, 3, 3, 3]
    return {"v3_credentials_from_B3": got, "v3_per_validator_counts": counts}


def test_p01_audit_example():
    """稽核的反例：B=3，子集 (0,1,2)(0,1,3)(0,2,3)(1,2,3)。v3 四張都過；v4 第四張的第一個部分簽章就被拒。"""
    L, vals = setup()
    A = root(L)
    L.open_batch(A.address, 3)
    subsets = [(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)]
    got = [cred(L, vals, s, A) for s in subsets[:3]]
    err = refused(lambda: cred(L, vals, subsets[3], A))
    assert len(got) == 3 and err and "budget" in err
    assert L.issued[A.address] == 9 and L.outstanding[A.address] == 9
    return {"credentials_obtained": len(got), "fourth_refused": err}


def test_p01_random_strategies(trials=60, seed=7):
    """隨機策略：任意子集、任意放棄，完整憑證數永遠 ≤ B。"""
    rng = random.Random(seed)
    worst = 0.0
    for _ in range(trials):
        L, vals = setup()
        A = root(L)
        B = rng.randint(1, 4)
        L.open_batch(A.address, B)
        partial = {}
        while L.can_issue(A.address):
            key = rng.randrange(B + 3)               # 同一個 m 可以分好幾次湊，也可以湊一半就放棄
            have = partial.setdefault(key, set())
            free = [i for i in range(4) if i not in have]
            if not free:
                continue
            i = rng.choice(free)
            F.obtain_credential([vals[i]], L, A, bytes([key]) * 20)
            have.add(i)
        complete = sum(1 for s in partial.values() if len(s) >= F.T)
        assert complete <= B, (B, complete)
        worst = max(worst, complete / B)
    return {"trials": trials, "max_credentials_over_B": worst}


def test_p01_negative_rating_cannot_be_dropped():
    """稽核的後果情境：負評那張的收據不交，只交回其餘未用憑證 → 清不了帳、開不了新批次。"""
    L, vals = setup()
    A, C = root(L), root(L)
    L.open_batch(A.address, 3)
    L.open_batch(C.address, 1)
    a = [cred(L, vals, s, A) for s in [(0, 1, 2), (1, 2, 3), (0, 2, 3)]]
    cp, cc = cred(L, vals, (0, 1, 3), C)
    trip(L, a[0][0], a[0][1], 5, cp, cc, 1)          # 駕駛 C 給乘客 A 1 分 → A 的假名 −2
    rets = [(p.address, s, F.return_proof(L, p, A.address)) for p, s in a[1:]]
    L.deposit(A.address, unused=rets)
    left = L.outstanding[A.address]
    err = refused(lambda: L.open_batch(A.address, 3))
    r, d, sg = F.obtain_receipt(vals[:3], L, a[0][0], A.address)
    L.deposit(A.address, receipts=[(r, d, sg)])
    assert left == 3 and err == "outstanding" and d == -2
    assert L.root_rep[A.address] == -2 and L.outstanding[A.address] == 0
    return {"outstanding_without_receipt": left, "open_batch": err, "rep_after_receipt": L.root_rep[A.address]}


# ------------------------------------------------------------------ P0-2
def test_p02_authorization():
    L, vals = setup()
    A = root(L)
    L.open_batch(A.address, 2)
    v = vals[0]
    out = {}
    # (a) 不是根私鑰簽的授權
    sid, R = v.cred_commit(A.address)
    req = F.BlindRequest(v.cred.P, R, b"\x01" * 20)
    bad = F.esign(Account.create().key, F.auth_digest(L.contract, L.chain_id, F.KIND_CRED, 1, 0, req.h))
    out["cred_wrong_key"] = refused(lambda: v.cred_respond(sid, req.e, bad))
    # (b) 用舊批次號簽的授權（批次號 0）
    sid, R = v.cred_commit(A.address)
    req = F.BlindRequest(v.cred.P, R, b"\x01" * 20)
    old = F.esign(A.key, F.auth_digest(L.contract, L.chain_id, F.KIND_CRED, 0, 0, req.h))
    out["cred_old_batch_nonce"] = refused(lambda: v.cred_respond(sid, req.e, old))
    # (c) 合法授權搬到另一次會談（h 不同）
    sid, R = v.cred_commit(A.address)
    req = F.BlindRequest(v.cred.P, R, b"\x01" * 20)
    good = F.esign(A.key, F.auth_digest(L.contract, L.chain_id, F.KIND_CRED, 1, 0, req.h))
    v.cred_respond(sid, req.e, good)
    sid2, R2 = v.cred_commit(A.address)
    req2 = F.BlindRequest(v.cred.P, R2, b"\x01" * 20)
    out["cred_replayed_auth"] = refused(lambda: v.cred_respond(sid2, req2.e, good))
    v.cred.abort()
    # (d) 不是登記的驗證節點直接記帳
    out["log_by_non_validator"] = refused(
        lambda: L.log_issue(F.Validator(0, L), A.address, b"\x00" * 32, good))
    # (e) 知道別人已結算的假名，用自己的金鑰申請收據
    C = root(L)
    L.open_batch(C.address, 1)
    ap, ac = cred(L, vals, (1, 2, 3), A)
    cp, cc = cred(L, vals, (0, 1, 2), C)
    trip(L, ap, ac, 5, cp, cc, 5)
    thief = Account.create()
    sid, d, R = vals[0].rcpt_commit(cp.address)
    req = F.BlindRequest(vals[0].receipt[d].P, R, F.receipt_serial(thief.address, b"\x02" * 32))
    au = F.esign(thief.key, F.auth_digest(L.contract, L.chain_id, F.KIND_RCPT, 0, 0, req.h))
    out["receipt_by_non_holder"] = refused(lambda: vals[0].rcpt_respond(sid, d, req.e, au))
    assert all(out.values()), out
    assert L.issued[A.address] == 4          # 只有合法的 1 次＋(e) 的 3 次被記帳
    return out


def test_p02_dataflow():
    """分兩段掃描驗證節點收到的參數與落地狀態：

    發憑證那段（驗證節點知道是哪個根身分）不得出現：假名 m、R'、未盲化挑戰值、最終簽章；
    發收據那段（驗證節點知道是哪個已結算假名，這是設計上公開的）不得出現：收據序號、r、R'、未盲化挑戰值、最終簽章。
    這兩段各自不漏，才代表「根身分 ↔ 假名」與「假名 ↔ 存入的收據」都連不起來。
    """
    with tempfile.TemporaryDirectory() as td:
        L, vals = setup(store_dir=td)
        A, C = root(L), root(L)
        L.open_batch(A.address, 2)
        L.open_batch(C.address, 1)
        phase = {"cred": [], "rcpt": []}
        cur = ["cred"]
        orig = F.BlindRequest.__init__

        def spy(self, P, R, m):
            orig(self, P, R, m)
            phase[cur[0]].extend([self.m, self.addrRp, self.e_unblinded])
        F.BlindRequest.__init__ = spy
        try:
            ap, ac = cred(L, vals, (0, 1, 2), A)
            ap2, ac2 = cred(L, vals, (1, 2, 3), A)
            cp, cc = cred(L, vals, (0, 2, 3), C)
            trip(L, ap, ac, 4, cp, cc, 5)
            cur[0] = "rcpt"
            rA = F.obtain_receipt(vals[:3], L, ap, A.address)
            rC = F.obtain_receipt(vals[1:], L, cp, C.address)
        finally:
            F.BlindRequest.__init__ = orig
        for _, (a, s) in ac + ac2 + cc:
            phase["cred"] += [a, s]
        for (r, d, sg), owner in ((rA, A), (rC, C)):
            phase["rcpt"] += [r, F.receipt_serial(owner.address, r)]
            phase["rcpt"] += [x for _, sig in sg for x in sig]

        def forms(x):
            return {x.hex()} if isinstance(x, bytes) else {str(x), hex(x)[2:]}

        def hay(prefix):
            out = []
            for v in vals:
                out += [" ".join(a.hex() if isinstance(a, bytes) else str(a) for a in t)
                        for t in v.transcript if t[0].startswith(prefix)]
                f = Path(td, f"v{v.idx}.json")
                if f.exists():
                    out += [k + json.dumps(rec) for k, rec in json.loads(f.read_text(encoding="utf-8")).items()
                            if k.startswith(prefix)]
            return "\n".join(out).lower()
        res = {}
        for ph in ("cred", "rcpt"):
            needles = set().union(*(forms(x) for x in phase[ph]))
            h = hay(ph)
            leaks = [n for n in needles if len(n) >= 16 and n.lower() in h]
            assert not leaks, (ph, leaks[:3])
            res[f"{ph}_secret_values_checked"] = len(needles)
        # 對照組：該出現的確實出現（掃描本身有效）
        assert A.address[2:].lower() in hay("cred") and ap.address[2:].lower() in hay("rcpt")
        res["validator_messages_scanned"] = sum(len(v.transcript) for v in vals)
        res["leaks"] = 0
        return res


# ------------------------------------------------------------------ P0-3
class FlakyLedger:
    """記帳交易其實已上鏈、但回覆前連線中斷：log_issue 做完再丟 ConnectionError。"""
    def __init__(self, L):
        self.L, self.fail_once = L, True

    def __getattr__(self, k):
        return getattr(self.L, k)

    def log_issue(self, *a):
        self.L.log_issue(*a)
        if self.fail_once:
            self.fail_once = False
            raise ConnectionError("RPC dropped after the log transaction was mined")


def test_p03_restart_and_retry():
    out = {}
    with tempfile.TemporaryDirectory() as td:
        L, vals = setup(store_dir=td)
        A, C = root(L), root(L)
        L.open_batch(A.address, 2)
        L.open_batch(C.address, 1)
        ap, ac = cred(L, vals, (0, 1, 2), A)
        cp, cc = cred(L, vals, (1, 2, 3), C)
        trip(L, ap, ac, 5, cp, cc, 5)
        F.obtain_receipt(vals[:3], L, ap, A.address)
        # (a) 驗證節點 0 重啟（新實例、同金鑰、同狀態檔），同一個假名再領 → 鏈上帳拒絕
        v0 = F.Validator(0, L, store_path=Path(td) / "v0.json", keys=vals[0].keys(), account=vals[0].account)
        out["second_receipt_after_restart"] = refused(lambda: v0.rcpt_commit(ap.address))
        # (b) 第 4 個節點也想對同一假名發（每假名最多 3 個部分簽章）
        out["fourth_validator_receipt"] = refused(lambda: vals[3].rcpt_commit(ap.address))
        # (c) 記帳已上鏈、回覆前斷線 → 重啟後同一個 (sid, e) 重試，拿到同一個 s，只記一次帳
        flaky = FlakyLedger(L)
        v1 = F.Validator(1, flaky, store_path=Path(td) / "v1.json", keys=vals[1].keys(), account=vals[1].account)
        p = Account.create()
        sid, R = v1.cred_commit(A.address)
        req = F.BlindRequest(v1.cred.P, R, m_of(p))
        auth = F.esign(A.key, F.auth_digest(L.contract, L.chain_id, F.KIND_CRED, L.batch_nonce(A.address), 1, req.h))
        before = L.outstanding[A.address]
        try:
            v1.cred_respond(sid, req.e, auth)
        except ConnectionError:
            pass
        v1b = F.Validator(1, L, store_path=Path(td) / "v1.json", keys=vals[1].keys(), account=vals[1].account)
        sig = req.finish(v1b.cred_respond(sid, req.e, auth))
        out["retry_after_crash_valid_sig"] = F.verify(v1.cred.P, m_of(p), sig)
        out["logged_once"] = L.outstanding[A.address] - before == 1
        # (d) 同一個會談換一個挑戰值 → 拒絕（同一個 nonce 只回答一個 e）
        out["same_session_other_challenge"] = refused(lambda: v1b.cred_respond(sid, (req.e + 1) % F.N, auth))
        # (e) 重啟時還沒收到 e 的會談作廢
        sid3, _ = vals[2].cred_commit(A.address)
        v2b = F.Validator(2, L, store_path=Path(td) / "v2.json", keys=vals[2].keys(), account=vals[2].account)
        out["open_session_dropped_on_restart"] = refused(lambda: v2b.cred_respond(sid3, 1, auth))
    assert all(out.values()), out
    return out


def test_ros_single_open_session():
    L, vals = setup()
    A = root(L)
    L.open_batch(A.address, 2)
    v = vals[0]
    sid, _ = v.cred_commit(A.address)
    out = {"concurrent_commit": refused(lambda: v.cred_commit(A.address))}
    old = F.SESSION_TIMEOUT_S
    F.SESSION_TIMEOUT_S = 0.0
    try:
        v.cred_commit(A.address)                  # 逾時：舊會談作廢、nonce 丟棄
        out["expired_session_answer"] = refused(lambda: v.cred_respond(sid, 1, b"\x00" * 65))
    finally:
        F.SESSION_TIMEOUT_S = old
        v.cred.abort()
    assert all(out.values()), out
    return out


# ------------------------------------------------------------------ P1
def test_p1_receipt_binding_and_swap():
    L, vals = setup()
    A, B = root(L), root(L)
    L.open_batch(A.address, 2)
    L.open_batch(B.address, 2)
    ap, ac = cred(L, vals, (0, 1, 2), A)
    ap2, ac2 = cred(L, vals, (0, 1, 3), A)
    bp, bc = cred(L, vals, (1, 2, 3), B)
    bp2, bc2 = cred(L, vals, (0, 2, 3), B)
    trip(L, ap, ac, 5, bp, bc, 1)                 # A 的假名 −2、B 的假名 +2
    out = {}
    rA = F.obtain_receipt(vals[:3], L, ap, A.address)
    out["deposit_others_receipt"] = refused(lambda: L.deposit(B.address, receipts=[rA]))
    proofA = F.return_proof(L, ap2, A.address)
    out["front_run_unused_return"] = refused(lambda: L.deposit(B.address, unused=[(ap2.address, ac2, proofA)]))
    # 兩個根身分事先講好互換：A 的 −2 收據綁 B、B 的 +2 收據綁 A（P1 的殘餘風險，總和守恆）
    L2, v2 = setup()
    X, Y = root(L2), root(L2)
    L2.open_batch(X.address, 1)
    L2.open_batch(Y.address, 1)
    xp, xc = cred(L2, v2, (0, 1, 2), X)
    yp, yc = cred(L2, v2, (1, 2, 3), Y)
    trip(L2, xp, xc, 5, yp, yc, 1)
    rx = F.obtain_receipt(v2[:3], L2, xp, Y.address)       # −2 綁到 Y
    ry = F.obtain_receipt(v2[1:], L2, yp, X.address)       # +2 綁到 X
    L2.deposit(X.address, receipts=[ry])
    L2.deposit(Y.address, receipts=[rx])
    out["swap_X_Y"] = [L2.root_rep[X.address], L2.root_rep[Y.address]]
    out["swap_sum_conserved"] = sum(out["swap_X_Y"]) == L2.delta[xp.address] + L2.delta[yp.address]
    assert out["deposit_others_receipt"] and out["front_run_unused_return"] and out["swap_sum_conserved"]
    return out


# ------------------------------------------------------------------ 正常流程
def test_happy_path_and_orphan_return():
    L, vals = setup()
    A, B = root(L), root(L)
    L.open_batch(A.address, 2)
    L.open_batch(B.address, 1)
    ap, ac = cred(L, vals, (0, 1, 2), A)
    bp, bc = cred(L, vals, (1, 2, 3), B)
    trip(L, ap, ac, 5, bp, bc, 4)
    # A 的第二張只拿到 2 個部分簽章就放棄（例如節點離線）→ 以 2 個單位交回
    op = Account.create()
    orphan = F.obtain_credential(vals[:2], L, A, m_of(op))
    L.deposit(A.address, receipts=[F.obtain_receipt(vals[1:], L, ap, A.address)],
              unused=[(op.address, orphan, F.return_proof(L, op, A.address))])
    L.deposit(B.address, receipts=[F.obtain_receipt(vals[:3], L, bp, B.address)])
    L.open_batch(A.address, 1)
    out = {"rep": [L.root_rep[A.address], L.root_rep[B.address]],
           "outstanding": [L.outstanding[A.address], L.outstanding[B.address]],
           "reopen_after_clearing": True}
    assert out["rep"] == [1, 2] and out["outstanding"] == [0, 0]
    return out


TESTS = [test_p01_v3_reproduces_audit, test_p01_audit_example, test_p01_random_strategies, test_p01_negative_rating_cannot_be_dropped,
         test_p02_authorization, test_p02_dataflow, test_p03_restart_and_retry, test_ros_single_open_session,
         test_p1_receipt_binding_and_swap, test_happy_path_and_orphan_return]


def main():
    res, ok = {}, True
    for t in TESTS:
        try:
            res[t.__name__] = {"pass": True, "detail": t()}
        except AssertionError as e:
            ok = False
            res[t.__name__] = {"pass": False, "detail": repr(e)}
        print(f"  {'PASS' if res[t.__name__]['pass'] else 'FAIL'}  {t.__name__}: {res[t.__name__]['detail']}")
    (HERE / "out").mkdir(exist_ok=True)
    json.dump(res, open(HERE / "out" / "v4_protocol_tests.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=str)
    print(f"{sum(r['pass'] for r in res.values())}/{len(res)} passed -> out/v4_protocol_tests.json")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
