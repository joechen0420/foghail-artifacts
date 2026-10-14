# -*- coding: utf-8 -*-
"""FogHail v3 憑證協定參考實作（2026-10-14，回應同事外審第 2 題與代理自查的問題）。

解決的問題（對照 docs/同事審閱提問回覆_*）：
  (a) 單一發行者      -> 4 個驗證節點各持一把發行金鑰，憑證需 t=3 把各自的盲簽章；
  (b) ROS 攻擊        -> 每個驗證節點同一時間只開一個盲簽流程（Issuer 內的鎖＋狀態檢查）；
  (c) 發行不檢查 R≥θ  -> 驗證節點發新一批憑證前，讀鏈上根身分信譽 R_root，未達 θ 拒發；
  (d) 信譽累積不到人   -> 每趟結算後，假名向驗證節點領一張「信譽收據」（依 ΔR 面額用不同金鑰盲簽），
                          使用者之後把收據存回根身分；收據序號經盲化，存入時無法連回假名；
  (e) 負評逃避        -> 根身分領 B 張憑證後，必須交回 B 件東西（收據或未用憑證）才能再領，
                          用過的憑證一定要交出它那一趟的收據，負評收據不能丟；
  (f) 鏈上可驗證      -> 挑戰值綁 R 的「地址」，合約用 ecrecover 技巧驗 Schnorr（見 verify()）。

曲線：secp256k1（EVM 原生）。簽章格式 (addrR', s')：e' = H(addrR' ‖ m)，驗 s'G − e'P 的地址 == addrR'。
盲化：R' = R + aG + bP，e = e' + b，s' = s + a。
"""
import hashlib
import secrets
import threading

from ecdsa import SECP256k1
from ecdsa.ellipticcurve import PointJacobi
from eth_utils import keccak

G = SECP256k1.generator
N = SECP256k1.order


def addr_of(P) -> bytes:
    """點 -> 以太坊地址（keccak(x‖y) 後 20 B）。"""
    return keccak(int(P.x()).to_bytes(32, "big") + int(P.y()).to_bytes(32, "big"))[12:]


def challenge(addrR: bytes, m: bytes) -> int:
    """e = keccak(addrR ‖ m) mod N（與合約 _schnorr 一致）。"""
    return int.from_bytes(keccak(addrR + m), "big") % N


def verify(P, m: bytes, sig) -> bool:
    addrR, s = sig
    e = challenge(addrR, m)
    Rv = s * G + (N - e) * P
    return addr_of(Rv) == addrR


def plain_sign(x: int, m: bytes):
    """非盲 Schnorr（只給量測腳本快速產生合法憑證用；驗證式與盲簽章相同）。"""
    k = secrets.randbelow(N - 1) + 1
    R = k * G
    a = addr_of(R)
    return a, (k + challenge(a, m) * x) % N


class Issuer:
    """一把發行金鑰。同一時間只允許一個盲簽流程（防 ROS）。"""
    def __init__(self, x=None):
        self.x = x or (secrets.randbelow(N - 1) + 1)
        self.P = self.x * G
        self._lock = threading.Lock()
        self._k = None

    def commit(self):
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("issuer busy: concurrent blind session refused (ROS)")
        self._k = secrets.randbelow(N - 1) + 1
        return self._k * G

    def respond(self, e: int) -> int:
        if self._k is None:
            raise RuntimeError("no open session")
        s = (self._k + e * self.x) % N
        self._k = None
        self._lock.release()
        return s

    def abort(self):
        if self._k is not None:
            self._k = None
            self._lock.release()


def blind_sign(issuer: Issuer, m: bytes):
    """使用者端一次盲簽流程，回傳 (addrR', s')；發行者看不到 m、addrR'、s'。"""
    R = issuer.commit()
    try:
        a = secrets.randbelow(N - 1) + 1
        b = secrets.randbelow(N - 1) + 1
        Rp = R + a * G + b * issuer.P
        addrRp = addr_of(Rp)
        e_p = challenge(addrRp, m)
        s = issuer.respond((e_p + b) % N)
    except Exception:
        issuer.abort()
        raise
    return addrRp, (s + a) % N


# ---------------------------------------------------------------- 驗證節點
DELTAS = (-2, -1, 0, 1, 2)          # 收據面額 = ΔR(status, rating)


class Validator:
    """一個驗證節點：一把憑證金鑰＋每個面額一把收據金鑰；規則全由鏈上狀態判定。"""
    def __init__(self, idx):
        self.idx = idx
        self.cred = Issuer()
        self.receipt = {d: Issuer() for d in DELTAS}
        self.signed_batch = {}      # (root, batchNonce) -> 已簽張數
        self.receipted = set()      # 已發過收據的假名

    def issue_credential(self, chain, root: bytes, m: bytes, session):
        """chain：讀鏈上狀態的介面（root_rep / outstanding / batch_nonce / theta）。"""
        if chain.root_rep(root) < chain.theta():
            raise PermissionError(f"V{self.idx}: R_root < θ, refuse")
        nonce, size = chain.batch(root)
        key = (root, nonce)
        if size == 0 or self.signed_batch.get(key, 0) >= size:
            raise PermissionError(f"V{self.idx}: batch not open or exhausted")
        self.signed_batch[key] = self.signed_batch.get(key, 0) + 1
        return session(self.cred, m)

    def issue_receipt(self, chain, pseudonym: bytes, m: bytes, session):
        d = chain.pending_receipt(pseudonym)
        if d is None:
            raise PermissionError(f"V{self.idx}: no settled trip for this pseudonym")
        if pseudonym in self.receipted:
            raise PermissionError(f"V{self.idx}: receipt already issued")
        self.receipted.add(pseudonym)
        return d, session(self.receipt[d], m)


def fresh_serial() -> bytes:
    return secrets.token_bytes(32)


def h(*parts) -> bytes:
    return hashlib.sha256(b"|".join(parts)).digest()
