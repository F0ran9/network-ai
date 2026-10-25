#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit.py — 平台操作审计日志模块 (等保 2.0: 操作可追溯)

存储层: SQLite (backend/audit.db), 同时双写 JSONL (backend/audit.log)
便于 grep / 导入 SIEM。

特性:
- 所有真机相关操作 (登录/改密/下发/回滚/验收/发现) 逐条落库
- 通过 contextvar 自动捕获操作者 IP (auth_middleware 中 set_context 注入)
- query(): 按动作/结果/主机/时间范围过滤 + 分页
- export_csv(): 导出 CSV
任何审计写入异常都不允许影响主流程。
"""
import contextvars
import csv
import datetime
import io
import json
import pathlib
import sqlite3
import threading

_backend_dir = pathlib.Path(__file__).parent
AUDIT_LOG = _backend_dir / "audit.log"       # JSON Lines (兼容旧格式, 便于 SIEM)
AUDIT_DB = _backend_dir / "audit.db"         # SQLite 主存储

_lock = threading.Lock()
_db_lock = threading.Lock()

# 请求级上下文: 由 auth_middleware 注入, audit() 自动带上操作者 IP
_client_ip_var: contextvars.ContextVar[str] = contextvars.ContextVar("audit_client_ip", default="")
_token_var: contextvars.ContextVar[str] = contextvars.ContextVar("audit_token", default="")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,             -- YYYY-MM-DD HH:MM:SS
    action      TEXT NOT NULL,             -- login / change-password / push / push-batch / rollback / ping-test / state / inspect / discover / api
    host        TEXT DEFAULT '',           -- 目标设备 IP (login 时为操作者 IP)
    device_type TEXT DEFAULT '',
    result      TEXT DEFAULT 'success',    -- success / fail / dry-run
    detail      TEXT DEFAULT '',
    commands    INTEGER,                   -- 命令条数 (可空)
    backup_file TEXT DEFAULT '',
    client_ip   TEXT DEFAULT '',           -- 操作者来源 IP
    session_id  TEXT DEFAULT ''            -- 会话 token 前 8 位 (脱敏)
);
CREATE INDEX IF NOT EXISTS idx_audit_ts     ON audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_host   ON audit_log(host);
"""


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(AUDIT_DB, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    try:
        with _db() as conn:
            conn.executescript(_SCHEMA)
    except Exception:
        pass


_init_db()


def set_context(client_ip: str, token: str = ""):
    """auth_middleware 每个请求调用一次, 让本请求后续 audit() 自动带操作者信息."""
    try:
        _client_ip_var.set(client_ip or "")
        _token_var.set((token or "")[:8])
    except Exception:
        pass


def audit(action: str, result: str = "success", host: str = "",
          device_type: str = "", detail: str = "",
          command_count=None, backup_file=None) -> dict:
    """追加一条审计记录 (SQLite + JSONL 双写). 任何异常都不允许影响主流程."""
    entry = {
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,          # login / change-password / push / rollback / ping-test / state / discover
        "host": host,
        "deviceType": device_type,
        "result": result,          # success / fail / dry-run
        "detail": str(detail)[:500],
        "clientIp": _client_ip_var.get() or host or "",
        "sessionId": _token_var.get(),
    }
    if command_count is not None:
        entry["commands"] = command_count
    if backup_file:
        entry["backupFile"] = backup_file

    # 1) JSONL 双写 (兼容旧查询路径 / SIEM)
    try:
        with _lock:
            with open(AUDIT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

    # 2) SQLite 主存储
    try:
        with _db_lock, _db() as conn:
            conn.execute(
                "INSERT INTO audit_log (ts, action, host, device_type, result, detail,"
                " commands, backup_file, client_ip, session_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (entry["time"], action, host or "", device_type or "", result,
                 entry["detail"], command_count, backup_file or "",
                 entry["clientIp"], entry["sessionId"]))
            conn.commit()
    except Exception:
        pass
    return entry


def _row_to_entry(r: sqlite3.Row) -> dict:
    e = {
        "time": r["ts"], "action": r["action"], "host": r["host"],
        "deviceType": r["device_type"], "result": r["result"], "detail": r["detail"],
        "clientIp": r["client_ip"], "sessionId": r["session_id"],
    }
    if r["commands"] is not None:
        e["commands"] = r["commands"]
    if r["backup_file"]:
        e["backupFile"] = r["backup_file"]
    return e


def recent(limit: int = 200) -> list:
    """返回最近 limit 条审计记录 (新→旧). 优先读 SQLite, 失败回退 JSONL."""
    try:
        with _db_lock, _db() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            if rows:
                return [_row_to_entry(r) for r in rows]
    except Exception:
        pass
    # 回退: 旧 JSONL
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


def query(action: str = "", result: str = "", host: str = "",
          keyword: str = "", start: str = "", end: str = "",
          page: int = 1, page_size: int = 20) -> dict:
    """条件过滤 + 分页查询. start/end 格式 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS."""
    where, params = [], []
    if action:
        where.append("action = ?"); params.append(action)
    if result:
        where.append("result = ?"); params.append(result)
    if host:
        where.append("(host LIKE ? OR client_ip LIKE ?)")
        params += [f"%{host}%", f"%{host}%"]
    if keyword:
        where.append("detail LIKE ?"); params.append(f"%{keyword}%")
    if start:
        where.append("ts >= ?"); params.append(f"{start[:10]} 00:00:00" if len(start) <= 10 else start)
    if end:
        where.append("ts <= ?"); params.append(f"{end[:10]} 23:59:59" if len(end) <= 10 else end)
    cond = (" WHERE " + " AND ".join(where)) if where else ""
    page = max(1, page); page_size = min(max(1, page_size), 200)
    with _db_lock, _db() as conn:
        total = conn.execute(f"SELECT COUNT(*) c FROM audit_log{cond}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM audit_log{cond} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [page_size, (page - 1) * page_size]).fetchall()
    return {"total": total, "page": page, "pageSize": page_size,
            "items": [_row_to_entry(r) for r in rows]}


def actions() -> list:
    """返回出现过的动作类型及计数 (用于前端筛选下拉)."""
    try:
        with _db_lock, _db() as conn:
            rows = conn.execute(
                "SELECT action, COUNT(*) c FROM audit_log GROUP BY action ORDER BY c DESC").fetchall()
            return [{"action": r["action"], "count": r["c"]} for r in rows]
    except Exception:
        return []


def export_csv(action: str = "", result: str = "", host: str = "",
               keyword: str = "", start: str = "", end: str = "") -> str:
    """按过滤条件导出 CSV 文本 (UTF-8 BOM, Excel 直接打开不乱码)."""
    data = query(action=action, result=result, host=host, keyword=keyword,
                 start=start, end=end, page=1, page_size=200)
    buf = io.StringIO()
    buf.write("\ufeff")
    w = csv.writer(buf)
    w.writerow(["时间", "动作", "目标主机", "设备类型", "结果", "操作者IP", "会话", "命令数", "备份文件", "详情"])
    items = data["items"]
    # 大结果分页拉全
    total = data["total"]
    fetched = len(items)
    page = 2
    while fetched < min(total, 5000):
        more = query(action=action, result=result, host=host, keyword=keyword,
                     start=start, end=end, page=page, page_size=200)
        if not more["items"]:
            break
        items += more["items"]
        fetched += len(more["items"])
        page += 1
    for e in items:
        w.writerow([e.get("time"), e.get("action"), e.get("host"), e.get("deviceType"),
                    e.get("result"), e.get("clientIp"), e.get("sessionId"),
                    e.get("commands", ""), e.get("backupFile", ""), e.get("detail")])
    return buf.getvalue()


def stats(days: int = 7) -> dict:
    """近 N 天操作统计 (前端看板用): 按天按动作计数."""
    try:
        since = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
        with _db_lock, _db() as conn:
            by_day = conn.execute(
                "SELECT substr(ts,1,10) d, COUNT(*) c FROM audit_log WHERE ts>=? GROUP BY d ORDER BY d",
                (since,)).fetchall()
            by_action = conn.execute(
                "SELECT action, COUNT(*) c FROM audit_log WHERE ts>=? GROUP BY action ORDER BY c DESC",
                (since,)).fetchall()
            fails = conn.execute(
                "SELECT COUNT(*) c FROM audit_log WHERE ts>=? AND result='fail'", (since,)).fetchone()["c"]
        return {"days": days,
                "byDay": [{"date": r["d"], "count": r["c"]} for r in by_day],
                "byAction": [{"action": r["action"], "count": r["c"]} for r in by_action],
                "fails": fails}
    except Exception:
        return {"days": days, "byDay": [], "byAction": [], "fails": 0}
