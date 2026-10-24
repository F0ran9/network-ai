#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit.py — 平台操作审计日志 (等保 2.0: 操作可追溯)
所有真机相关操作 (登录/改密/下发/回滚/验收/发现) 逐条追加到 backend/audit.log,
JSON Lines 格式, 一行一条, 便于 grep / 导入 SIEM。
"""
import datetime
import json
import pathlib
import threading

AUDIT_LOG = pathlib.Path(__file__).parent / "audit.log"
_lock = threading.Lock()


def audit(action: str, result: str = "success", host: str = "",
          device_type: str = "", detail: str = "",
          command_count=None, backup_file=None) -> dict:
    """追加一条审计记录. 任何异常都不允许影响主流程."""
    entry = {
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,          # login / change-password / push / rollback / ping-test / state / discover
        "host": host,
        "deviceType": device_type,
        "result": result,          # success / fail / dry-run
        "detail": str(detail)[:300],
    }
    if command_count is not None:
        entry["commands"] = command_count
    if backup_file:
        entry["backupFile"] = backup_file
    try:
        with _lock:
            with open(AUDIT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return entry


def recent(limit: int = 200) -> list:
    """返回最近 limit 条审计记录 (新→旧)."""
    try:
        with _lock:
            if not AUDIT_LOG.exists():
                return []
            lines = AUDIT_LOG.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out = []
    for line in reversed(lines):
        if len(out) >= limit:
            break
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out
