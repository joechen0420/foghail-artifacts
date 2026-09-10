# -*- coding: utf-8 -*-
"""加鹽布隆過濾器（以 Python 大整數為位元陣列）＝ FogHail 霧節點媒合器核心。

一個 BF 就是一個 m-bit 整數；插入 = OR 對應位元；交集 = AND；
C_int = popcount(AND)。cell -> 位元遮罩以 memoize 加速（同 cell 只算一次）。

此檔為論文霧節點的實際參考實作，只用 Python 標準庫（hashlib、functools）。
"""
import hashlib
from functools import lru_cache


class BF:
    def __init__(self, m, k, salt):
        self.m = m
        self.k = k
        self.salt = salt
        self._cache = {}

    def cell_bits(self, cell):
        """回傳一個 cell 的 m-bit 遮罩（k 個雜湊位元；內部碰撞會 < k）。"""
        v = self._cache.get(cell)
        if v is not None:
            return v
        gx, gy = cell
        mask = 0
        base = f"{gx},{gy}|{self.salt}".encode()
        for i in range(self.k):
            h = hashlib.blake2b(base + b"|" + str(i).encode(), digest_size=8).digest()
            idx = int.from_bytes(h, "little") % self.m
            mask |= (1 << idx)
        self._cache[cell] = mask
        return mask

    def build(self, cells):
        """把多個 cell 併成一個 BF（union = OR）。"""
        bf = 0
        for c in cells:
            bf |= self.cell_bits(c)
        return bf

    @staticmethod
    def intersect_count(bf_a, bf_b):
        return (bf_a & bf_b).bit_count()

    def is_match(self, bf_driver, bf_rider, driver_mask=None):
        """論文判定：C_int >= k。
        更嚴謹的成員判定為 (bf_driver AND bf_rider) == bf_driver，
        可避免 k 個雜湊內部碰撞造成的偽陰性；driver_mask 傳入時採用之。"""
        c_int = (bf_driver & bf_rider).bit_count()
        if driver_mask is not None:
            return (bf_driver & bf_rider) == driver_mask, c_int
        return c_int >= self.k, c_int


def theoretical_fpr(m, k, n):
    """單一非成員元素的理論偽陽率 (1 - e^(-kn/m))^k。n=插入元素數（乘客 9 格）。"""
    import math
    return (1 - math.exp(-k * n / m)) ** k
