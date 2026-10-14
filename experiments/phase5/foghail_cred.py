# -*- coding: utf-8 -*-
"""FogHail v4 憑證協定參考實作（2026-10-14，回應 Code_Audit_2026-10-14 的 P0-1、P0-2、P0-3、P1）。

v3 的版本留在 foghail_cred_v3.py（run_e6_v3.py 那次量測用的就是它）。

v3 → v4 改了什麼：
  P0-1 配額混用   v3 每個驗證節點各自限簽 B 次，4 個節點 × B 次 ÷ 每張 3 個 = 可湊出 4B/3 張。
                  v4 改成「整批共用預算」：openBatch(B) 給 T·B = 3B 個部分簽章，每簽一個都先上鏈記帳，
                  合約在第 3B+1 個拒絕。每張憑證要 3 個部分簽章，所以不管怎麼混用節點子集合，最多 B 張。
  P0-2 持有人授權 申請憑證要附「根私鑰」對 (合約, 鏈, 種類, 批次號, 節點編號, 會談雜湊 h) 的簽章；
                  申請收據要附「假名私鑰」的同一種簽章。h = keccak(R, e) 綁住這一次盲簽會談，不能重播。
                  驗證節點對外只有 commit / respond 兩個方法，收到的只有 (根或假名地址, 會談編號, 盲化挑戰值 e, 授權簽章)，
                  m（假名地址）與收據序號從頭到尾不經過驗證節點；transcript 會把收到的每個參數記下來給測試掃描。
  P0-3 持久化     發行記錄寫在鏈上（logIssue / logReceipt），合約強制配額，重啟、換實例、多實例都共用同一份帳。
                  每個假名最多 T 個收據部分簽章（每節點一個），所以同一趟結算領不到第二張收據。
                  驗證節點的會談 nonce 先寫進磁碟再回 R；回應前先把 e 寫進磁碟（write-ahead），
                  當機後同一個 (R, e) 重試會得到同一個 s，換一個 e 一律拒絕——同一個 nonce 永遠只回答一個挑戰值。
  P1  收據移轉    收據序號 = keccak(根身分地址 ‖ r)，存入時合約用 msg.sender 重算，所以別人搶不走、也不能搶先存入；
                  交回未用憑證要附假名對 (合約, 鏈, "return", 根) 的簽章。兩個根身分事先講好互換收據仍然做得到，
                  但總和守恆（一方加多少，另一方就少多少），見 test_foghail_cred.py 的 swap 測試與論文 §7。

ROS：每把金鑰同一時間只有一個「已給出 R、還沒收到 e」的會談；逾時（SESSION_TIMEOUT_S）作廢、nonce 丟棄。

曲線：secp256k1（EVM 原生）。簽章格式 (addrR', s')：e' = H(addrR' ‖ m)，驗 s'G − e'P 的地址 == addrR'。
盲化：R' = R + aG + bP，e = e' + b，s' = s + a。
"""
import json
import os
import secrets
import threading
import time
from pathlib import Path

from ecdsa import SECP256k1
from eth_abi import encode as abi_encode
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import keccak

G = SECP256k1.generator
N = SECP256k1.order
T, V = 3, 4                          # 門檻：4 個驗證節點中要 3 個
DELTAS = (-2, -1, 0, 1, 2)           # 收據面額 = ΔR(status, rating)
KIND_CRED = keccak(b"FOGHAIL_CRED")  # 與合約常數一致
KIND_RCPT = keccak(b"FOGHAIL_RCPT")
KIND_RETURN = keccak(b"FOGHAIL_RETURN")
SESSION_TIMEOUT_S = 30.0


# ---------------------------------------------------------------- Schnorr（與合約 _schnorr 一致）
def addr_of(P) -> bytes:
    """點 -> 以太坊地址（keccak(x‖y) 後 20 B）。"""
    return keccak(int(P.x()).to_bytes(32, "big") + int(P.y()).to_bytes(32, "big"))[12:]


def challenge(addrR: bytes, m: bytes) -> int:
    """e = keccak(addrR ‖ m) mod N。"""
    return int.from_bytes(keccak(addrR + m), "big") % N


def verify(P, m: bytes, sig) -> bool:
    addrR, s = sig
    e = challenge(addrR, m)
    Rv = s * G + (N - e) * P
    return addr_of(Rv) == addrR


def plain_sign(x: int, m: bytes):
    """非盲 Schnorr（只給量測腳本快速產生合法憑證用；驗證式與盲簽章相同）。"""
    k = secrets.randbelow(N - 1) + 1
    a = addr_of(k * G)
    return a, (k + challenge(a, m) * x) % N


def rand_scalar() -> int:
    return secrets.randbelow(N - 1) + 1


# ---------------------------------------------------------------- 授權與綁定（與合約 authDigest 等一致）
def session_hash(R, e: int) -> bytes:
    """h = keccak(R.x ‖ R.y ‖ e)：一次盲簽會談的識別碼，授權簽章與鏈上記帳都綁它。"""
    return keccak(abi_encode(["uint256", "uint256", "uint256"], [int(R.x()), int(R.y()), e]))


def auth_digest(contract: str, chain_id: int, kind: bytes, ctx: int, v: int, h: bytes) -> bytes:
    return keccak(abi_encode(["address", "uint256", "bytes32", "uint256", "uint8", "bytes32"],
                             [contract, chain_id, kind, ctx, v, h]))


def return_digest(contract: str, chain_id: int, root: str) -> bytes:
    return keccak(abi_encode(["address", "uint256", "bytes32", "address"],
                             [contract, chain_id, KIND_RETURN, root]))


def receipt_serial(root: str, r: bytes) -> bytes:
    """收據序號綁根身分：serial = keccak(root ‖ r)，合約存入時以 msg.sender 重算。"""
    return keccak(abi_encode(["address", "bytes32"], [root, r]))


def esign(key, digest: bytes) -> bytes:
    return bytes(Account.sign_message(encode_defunct(primitive=digest), key).signature)


def erecover(digest: bytes, sig: bytes) -> str:
    return Account.recover_message(encode_defunct(primitive=digest), signature=sig)


# ---------------------------------------------------------------- 會談狀態的持久化
class MemoryStore:
    """不落地的狀態（量測、單元測試用）。"""
    def __init__(self):
        self.d = {}

    def get(self, k):
        return self.d.get(k)

    def put(self, k, v):
        self.d[k] = v

    def delete(self, k):
        self.d.pop(k, None)

    def items(self):
        return list(self.d.items())


class JsonStore(MemoryStore):
    """落地的狀態：每次寫入都整檔原子替換（tmp → os.replace），當機不會留下半個檔案。"""
    def __init__(self, path):
        super().__init__()
        self.path = Path(path)
        if self.path.exists():
            self.d = json.loads(self.path.read_text(encoding="utf-8"))

    def _flush(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.d), encoding="utf-8")
        os.replace(tmp, self.path)

    def put(self, k, v):
        super().put(k, v)
        self._flush()

    def delete(self, k):
        super().delete(k)
        self._flush()


# ---------------------------------------------------------------- 發行金鑰
class Issuer:
    """一把發行金鑰。同一時間只有一個「已給 R、未收 e」的會談（防 ROS）。

    respond 的順序：查授權與配額 → e 寫進磁碟 → 上鏈記帳 → 回 s。
    已寫過 e 的會談只會用同一個 e 重算同一個 s（當機重試），不會回答第二個 e。
    """
    def __init__(self, x=None, store=None, name="k"):
        self.x = x or rand_scalar()
        self.P = self.x * G
        self.store = store if store is not None else MemoryStore()
        self.name = name
        self._mu = threading.Lock()
        self._open = None                     # (sid, 開始時間)
        for k, rec in self.store.items():     # 重啟：還沒收到 e 的會談一律作廢
            if k.startswith(name + ":") and rec.get("e") is None:
                self.store.delete(k)

    def _key(self, sid):
        return f"{self.name}:{sid}"

    def commit(self, subject: str, extra=None):
        with self._mu:
            if self._open is not None:
                if time.monotonic() - self._open[1] < SESSION_TIMEOUT_S:
                    raise RuntimeError("issuer busy: concurrent blind session refused (ROS)")
                self.store.delete(self._key(self._open[0]))      # 逾時作廢，nonce 丟棄
                self._open = None
            k = rand_scalar()
            R = k * G
            sid = addr_of(R).hex()
            self.store.put(self._key(sid), {"k": hex(k), "e": None, "subject": subject, "extra": extra})
            self._open = (sid, time.monotonic())
            return sid, R

    def record(self, sid):
        return self.store.get(self._key(sid))

    def respond(self, sid: str, e: int, log=None, logged=None) -> int:
        """log(h)：上鏈記帳（違規時丟 PermissionError）；logged(h)：鏈上是否已記過。"""
        with self._mu:
            rec = self.store.get(self._key(sid))
            if rec is None:
                raise PermissionError("unknown or expired session")
            k = int(rec["k"], 16)
            h = session_hash(k * G, e)
            if rec["e"] is not None:                              # 重試
                if int(rec["e"], 16) != e:
                    raise PermissionError("session already answered another challenge")
                if log is not None and not (logged and logged(h)):
                    log(h)
                return (k + e * self.x) % N
            if self._open is None or self._open[0] != sid:
                raise PermissionError("session is not the open one")
            rec["e"] = hex(e)
            self.store.put(self._key(sid), rec)                   # write-ahead
            try:
                if log is not None:
                    log(h)
            except PermissionError:                               # 規則不允許：會談作廢
                self.store.delete(self._key(sid))
                self._open = None
                raise
            except Exception:
                # 網路／節點錯誤：記帳交易可能其實已上鏈，所以保留 (k, e) 讓同一個 e 重試；
                # e 已經固定，這個 R 不會再回答別的挑戰值，釋放鎖不影響 ROS 防護。
                self._open = None
                raise
            self._open = None
            return (k + e * self.x) % N

    def abort(self, sid=None):
        with self._mu:
            if self._open is not None and (sid is None or self._open[0] == sid):
                rec = self.store.get(self._key(self._open[0]))
                if rec is not None and rec.get("e") is None:
                    self.store.delete(self._key(self._open[0]))
                self._open = None


# ---------------------------------------------------------------- 使用者端
class BlindRequest:
    """使用者端的一次盲化：持有 m、a、b；只把 e 交給發行者。"""
    def __init__(self, P, R, m: bytes):
        self.P, self.m = P, m
        self.a, b = rand_scalar(), rand_scalar()
        self.addrRp = addr_of(R + self.a * G + b * P)
        self.e_unblinded = challenge(self.addrRp, m)
        self.e = (self.e_unblinded + b) % N
        self.h = session_hash(R, self.e)

    def finish(self, s: int, check=True):
        """去盲。check：使用者自己驗一次簽章（協定流程預設驗；成本量測與 v1 同口徑，不驗）。"""
        sig = (self.addrRp, (s + self.a) % N)
        if check and not verify(self.P, self.m, sig):
            raise ValueError("issuer returned an invalid blind signature")
        return sig


def blind_sign(issuer: Issuer, m: bytes):
    """本機一次盲簽（不記帳、不授權、不自驗；只給客戶端成本量測用，口徑同 v1 的 blind_issue）。"""
    sid, R = issuer.commit("bench")
    req = BlindRequest(issuer.P, R, m)
    return req.finish(issuer.respond(sid, req.e), check=False)


# ---------------------------------------------------------------- 驗證節點
class Validator:
    """一個驗證節點：一把憑證金鑰＋每個面額一把收據金鑰。

    規則全由 ledger（鏈上合約，或測試用的 LocalLedger）判定與記帳；驗證節點自己不留配額計數。
    對外介面只收 (根或假名地址, 會談編號, 盲化挑戰值, 授權簽章)。
    """
    def __init__(self, idx, ledger=None, store_path=None, keys=None, account=None):
        self.idx = idx
        self.ledger = ledger
        keys = keys or {}
        self.account = account or Account.create()      # 上鏈記帳用的帳戶（合約建構子登記）
        self.store = JsonStore(store_path) if store_path else MemoryStore()
        self.cred = Issuer(keys.get("cred"), self.store, "cred")
        self.receipt = {d: Issuer(keys.get(d), self.store, f"rcpt{d}") for d in DELTAS}
        self.transcript = []                             # 收到的每一個參數（資料流檢查用）

    def keys(self):
        return {"cred": self.cred.x, **{d: self.receipt[d].x for d in DELTAS}}

    def _see(self, op, *args):
        self.transcript.append((op,) + args)

    # 憑證：根身分申請
    def cred_commit(self, root: str):
        self._see("cred_commit", root)
        if not self.ledger.can_issue(root):
            raise PermissionError(f"V{self.idx}: batch not open or budget exhausted")
        return self.cred.commit(root)

    def cred_respond(self, sid: str, e: int, auth: bytes) -> int:
        self._see("cred_respond", sid, e, auth)
        rec = self.cred.record(sid)
        if rec is None:
            raise PermissionError(f"V{self.idx}: unknown or expired session")
        root = rec["subject"]

        def log(h):
            ctx = self.ledger.batch_nonce(root)
            d = auth_digest(self.ledger.contract, self.ledger.chain_id, KIND_CRED, ctx, self.idx, h)
            if erecover(d, auth) != root:
                raise PermissionError(f"V{self.idx}: root authorization invalid")
            self.ledger.log_issue(self, root, h, auth)
        return self.cred.respond(sid, e, log, self.ledger.session_logged)

    # 收據：假名申請
    def rcpt_commit(self, pseudonym: str):
        self._see("rcpt_commit", pseudonym)
        d = self.ledger.pending_delta(pseudonym)
        if d is None:
            raise PermissionError(f"V{self.idx}: no settled trip for this pseudonym")
        if not self.ledger.can_receipt(pseudonym, self.idx):
            raise PermissionError(f"V{self.idx}: receipt already issued")
        sid, R = self.receipt[d].commit(pseudonym, d)
        return sid, d, R

    def rcpt_respond(self, sid: str, d: int, e: int, auth: bytes) -> int:
        self._see("rcpt_respond", sid, d, e, auth)
        iss = self.receipt[d]
        rec = iss.record(sid)
        if rec is None or rec["extra"] != d:
            raise PermissionError(f"V{self.idx}: unknown or expired session")
        p = rec["subject"]

        def log(h):
            dg = auth_digest(self.ledger.contract, self.ledger.chain_id, KIND_RCPT, 0, self.idx, h)
            if erecover(dg, auth) != p:
                raise PermissionError(f"V{self.idx}: pseudonym authorization invalid")
            self.ledger.log_receipt(self, p, h, auth)
        return iss.respond(sid, e, log, self.ledger.session_logged)


# ---------------------------------------------------------------- 持有人端流程
def obtain_credential(validators, ledger, root_acct, m: bytes):
    """根身分向給定的 3 個驗證節點各做一次盲簽；回傳 [(idx, (addrR', s'))]。"""
    sigs = []
    for v in validators:
        sid, R = v.cred_commit(root_acct.address)
        req = BlindRequest(v.cred.P, R, m)
        ctx = ledger.batch_nonce(root_acct.address)
        auth = esign(root_acct.key, auth_digest(ledger.contract, ledger.chain_id, KIND_CRED, ctx, v.idx, req.h))
        sigs.append((v.idx, req.finish(v.cred_respond(sid, req.e, auth))))
    return sigs


def obtain_receipt(validators, ledger, pseudo_acct, root_addr: str):
    """假名向 3 個驗證節點領收據；序號綁 root_addr。回傳 (r, ΔR, [(idx, sig)])。"""
    r = secrets.token_bytes(32)
    serial = receipt_serial(root_addr, r)
    sigs, d = [], None
    for v in validators:
        sid, d, R = v.rcpt_commit(pseudo_acct.address)
        req = BlindRequest(v.receipt[d].P, R, serial)
        auth = esign(pseudo_acct.key, auth_digest(ledger.contract, ledger.chain_id, KIND_RCPT, 0, v.idx, req.h))
        sigs.append((v.idx, req.finish(v.rcpt_respond(sid, d, req.e, auth))))
    return r, d, sigs


def return_proof(ledger, pseudo_acct, root_addr: str) -> bytes:
    """交回未用憑證時的持有證明：假名對 (合約, 鏈, "return", 根) 簽章。"""
    return esign(pseudo_acct.key, return_digest(ledger.contract, ledger.chain_id, root_addr))


# ---------------------------------------------------------------- 合約規則的 Python 鏡像（離線測試用）
class LocalLedger:
    """與 FogHailAttestation v4 相同的狀態與規則，純 Python，讓測試不必開鏈。

    鏈上版本見 phase4/contracts/FogHailAttestation.sol；run_e6_v4.py 在活鏈上重跑同一組關鍵測試。
    """
    def __init__(self, theta=0, contract="0x" + "11" * 20, chain_id=1337):
        self.contract, self.chain_id, self.theta = contract, chain_id, theta
        self.validators = {}               # 帳戶地址 -> idx
        self.cred_P, self.rcpt_P = {}, {}
        self.registered, self.root_rep, self.outstanding = set(), {}, {}
        self.nonce, self.budget, self.issued = {}, {}, {}
        self.session_used, self.rcpt_mask = set(), {}
        self.has_pending, self.delta = set(), {}
        self.pseudonym_spent, self.receipt_spent, self.trips = set(), set(), set()

    def add_validators(self, vals):
        for v in vals:
            self.validators[v.account.address] = v.idx
            self.cred_P[v.idx] = v.cred.P
            for d in DELTAS:
                self.rcpt_P[(d, v.idx)] = v.receipt[d].P

    # 讀
    def can_issue(self, root):
        return root in self.registered and self.issued.get(root, 0) < self.budget.get(root, 0)

    def batch_nonce(self, root):
        return self.nonce.get(root, 0)

    def session_logged(self, h):
        return h in self.session_used

    def pending_delta(self, p):
        return self.delta[p] if p in self.has_pending else None

    def can_receipt(self, p, idx):
        mask = self.rcpt_mask.get(p, 0)
        return not (mask >> idx) & 1 and bin(mask).count("1") < T

    # 寫（對應合約函式）
    def register_root(self, root):
        if root in self.registered:
            raise PermissionError("registered")
        self.registered.add(root)
        self.root_rep[root] = 0

    def open_batch(self, root, size):
        if root not in self.registered:
            raise PermissionError("not registered")
        if self.outstanding.get(root, 0) != 0:
            raise PermissionError("outstanding")
        if self.root_rep[root] < self.theta:
            raise PermissionError("reputation below theta")
        self.nonce[root] = self.nonce.get(root, 0) + 1
        self.budget[root], self.issued[root] = T * size, 0

    def _caller(self, validator):
        if validator.account.address not in self.validators:
            raise PermissionError("validator only")
        return self.validators[validator.account.address]

    def log_issue(self, validator, root, h, auth):
        v = self._caller(validator)
        if root not in self.registered:
            raise PermissionError("not registered")
        if self.issued.get(root, 0) >= self.budget.get(root, 0):
            raise PermissionError("batch budget")
        if h in self.session_used:
            raise PermissionError("session logged")
        d = auth_digest(self.contract, self.chain_id, KIND_CRED, self.nonce.get(root, 0), v, h)
        if erecover(d, auth) != root:
            raise PermissionError("root auth")
        self.session_used.add(h)
        self.issued[root] += 1
        self.outstanding[root] = self.outstanding.get(root, 0) + 1

    def log_receipt(self, validator, p, h, auth):
        v = self._caller(validator)
        if p not in self.has_pending:
            raise PermissionError("no settled trip")
        mask = self.rcpt_mask.get(p, 0)
        if (mask >> v) & 1:
            raise PermissionError("receipt logged")
        if bin(mask).count("1") >= T:
            raise PermissionError("receipt quota")
        if h in self.session_used:
            raise PermissionError("session logged")
        if erecover(auth_digest(self.contract, self.chain_id, KIND_RCPT, 0, v, h), auth) != p:
            raise PermissionError("pseudonym auth")
        self.session_used.add(h)
        self.rcpt_mask[p] = mask | (1 << v)

    def _check(self, keyof, m, sigs, exact=T):
        idxs = [i for i, _ in sigs]
        if (exact and len(sigs) != exact) or not 1 <= len(sigs) <= V or len(set(idxs)) != len(idxs):
            raise PermissionError("signer index")
        for i, s in sigs:
            if not verify(keyof(i), m, s):
                raise PermissionError("credential sig")

    def settle(self, trip, rider, driver, status=0):
        """rider/driver = (假名地址, 給對方的評分, [(idx, sig)]×3)。評分簽章與霧節點簽章在鏈上版本驗。"""
        if trip in self.trips:
            raise PermissionError("trip exists")
        for p, _, cred in (rider, driver):
            if p in self.pseudonym_spent:
                raise PermissionError("credential spent")
            self._check(lambda i: self.cred_P[i], bytes.fromhex(p[2:]), cred)
        self.trips.add(trip)
        for (p, _, _), gives in ((rider, driver[1]), (driver, rider[1])):
            self.pseudonym_spent.add(p)
            self.has_pending.add(p)
            self.delta[p] = -2 if status else gives - 3

    def deposit(self, root, receipts=(), unused=()):
        """receipts：[(r, ΔR, sigs×3)]；unused：[(假名地址, sigs×1..4, 持有證明)]。單位＝部分簽章。"""
        units, total, spent_r, spent_p = 0, 0, [], []
        for r, d, sigs in receipts:
            serial = receipt_serial(root, r)
            if serial in self.receipt_spent or serial in spent_r:
                raise PermissionError("receipt spent")
            self._check(lambda i: self.rcpt_P[(d, i)], serial, sigs)
            spent_r.append(serial)
            total += d
            units += T
        for p, sigs, proof in unused:
            if p in self.pseudonym_spent or p in spent_p:
                raise PermissionError("credential spent")
            if erecover(return_digest(self.contract, self.chain_id, root), proof) != p:
                raise PermissionError("possession")
            self._check(lambda i: self.cred_P[i], bytes.fromhex(p[2:]), sigs, exact=None)
            spent_p.append(p)
            units += len(sigs)
        if units == 0 or units > self.outstanding.get(root, 0):
            raise PermissionError("units")
        self.receipt_spent.update(spent_r)
        self.pseudonym_spent.update(spent_p)
        self.outstanding[root] -= units
        self.root_rep[root] += total
