# -*- coding: utf-8 -*-
"""Besu 看門狗：偵測 Besu 的 java 行程，若「記憶體超過門檻」或「執行超過時限」
就自動關閉並寫入日誌。**只針對 Besu 的 java 行程**（cmdline 含 besu），
絕不動其他 java 程式，符合安全規範。

用法：
    python besu_watchdog.py                       # 持續看守（每 30s 檢查）
    python besu_watchdog.py --once                # 檢查一次即結束（可排程/手動）
    python besu_watchdog.py --max-mem-mb 1500 --max-minutes 30 --interval 20
    python besu_watchdog.py --dry-run             # 只報告不關閉（先觀察）

日誌：besu_watchdog.log（與本檔同目錄），每次關閉/檢查追加一行。
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

sys.stdout.reconfigure(encoding="utf-8")
LOG = Path(__file__).resolve().parent / "besu_watchdog.log"


def _now():
    # 用系統時間字串（避免依賴不可用的時間 API）
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    line = f"[{_now()}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def besu_procs():
    """找出所有 Besu 的 java 行程（只認 cmdline 含 besu 者）。"""
    out = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "create_time", "memory_info"]):
        try:
            name = (p.info["name"] or "").lower()
            if "java" not in name:
                continue
            cmd = " ".join(p.info["cmdline"] or []).lower()
            if "besu" not in cmd:
                continue
            out.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


def kill_tree(pid):
    """關閉行程樹（Windows taskkill /T；只關指定 PID，不波及其他）。"""
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)


def check_once(max_mem_mb, max_minutes, dry_run):
    procs = besu_procs()
    if not procs:
        return 0
    killed = 0
    for p in procs:
        try:
            rss_mb = p.info["memory_info"].rss / (1024 * 1024)
            runtime_min = (time.time() - p.info["create_time"]) / 60.0
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        reason = None
        if rss_mb > max_mem_mb:
            reason = f"memory {rss_mb:.0f}MB > {max_mem_mb}MB"
        elif runtime_min > max_minutes:
            reason = f"runtime {runtime_min:.1f}min > {max_minutes}min"
        if reason:
            if dry_run:
                log(f"WOULD-KILL pid={p.pid} 因 {reason}（--dry-run 未實際關閉）")
            else:
                kill_tree(p.pid)
                log(f"KILLED pid={p.pid} 因 {reason}（mem={rss_mb:.0f}MB, run={runtime_min:.1f}min）")
                killed += 1
        else:
            log(f"OK pid={p.pid} mem={rss_mb:.0f}MB run={runtime_min:.1f}min（門檻 {max_mem_mb}MB/{max_minutes}min）")
    return killed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-mem-mb", type=int, default=2048, help="單一 Besu 行程記憶體上限 MB")
    ap.add_argument("--max-minutes", type=float, default=60.0, help="單一 Besu 行程執行時限（分）")
    ap.add_argument("--interval", type=float, default=30.0, help="持續模式的檢查間隔（秒）")
    ap.add_argument("--once", action="store_true", help="只檢查一次即結束")
    ap.add_argument("--dry-run", action="store_true", help="只報告不關閉")
    a = ap.parse_args()

    log(f"看門狗啟動：記憶體上限 {a.max_mem_mb}MB、時限 {a.max_minutes}min"
        + ("、只檢查一次" if a.once else f"、每 {a.interval}s 檢查")
        + ("、DRY-RUN" if a.dry_run else ""))
    if a.once:
        n = check_once(a.max_mem_mb, a.max_minutes, a.dry_run)
        log(f"單次檢查完成，關閉 {n} 個行程。")
        return
    try:
        while True:
            check_once(a.max_mem_mb, a.max_minutes, a.dry_run)
            time.sleep(a.interval)
    except KeyboardInterrupt:
        log("看門狗手動停止。")


if __name__ == "__main__":
    main()
