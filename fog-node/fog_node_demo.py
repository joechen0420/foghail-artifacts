# -*- coding: utf-8 -*-
"""FogHail 霧節點媒合示範 —— 讓你直觀看到這台 PC 當霧節點時做了什麼。

模擬一個批次窗：收到一個乘客請求（9 格布隆過濾器）＋一群駕駛心跳（各 1 格），
霧節點只用位元運算判斷誰配得上，全程不接觸座標。
"""
import random
from bloom import BF

M, K, SALT = 512, 5, "epoch-0001"


def neighborhood(gx, gy):
    return [(gx + dx, gy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]


def main():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    bf = BF(M, K, SALT)

    rider_cell = (250, 180)                       # 乘客上車格
    bf_p = bf.build(neighborhood(*rider_cell))    # 編 9 格 → BF_p

    drivers = {
        "D1": (250, 180),   # 同格 → 應 match
        "D2": (251, 181),   # 鄰域內 → 應 match
        "D3": (249, 179),   # 鄰域內 → 應 match
        "D4": (300, 200),   # 遠 → 不 match
        "D5": (400, 100),   # 遠 → 不 match
    }

    print("=" * 56)
    print("FogHail 霧節點媒合示範（一個批次窗）")
    print("=" * 56)
    print(f"乘客上車格 {rider_cell}，編碼 9 格鄰域為 BF_p（{M} bit = {M // 8} B）")
    print(f"每台駕駛只編自己 1 格，上傳 {M // 8} B 布隆過濾器\n")
    print("霧節點盲測判定（只做位元 AND + 比較，看不到座標）：")

    matched = []
    for name, cell in drivers.items():
        bf_d = bf.cell_bits(cell)
        ok, c_int = bf.is_match(bf_d, bf_p, driver_mask=bf_d)   # 精確成員測試
        print(f"  {name}: {'MATCH   ' if ok else 'no match'}  (重疊位元 C_int={c_int})")
        if ok:
            matched.append(name)

    print(f"\n配到的駕駛：{matched}")
    if matched:
        winner = random.Random(0).choice(matched)
        print(f"加權隨機選定 → {winner}（霧節點無距離資訊，不排序）")
        print("→ 轉發雙方臨時公鑰，由乘客與駕駛自建 ECDH 加密通道交換精確位置")
    print("=" * 56)


if __name__ == "__main__":
    main()
