#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
device_connector.py — 真机连接层 (netmiko)
提供三类能力, 供 main.py 的 API 调用:
  1. push_config()      备份当前配置 → (dry-run) 预览 / 真实下发 → 保存
  2. run_ping_tests()   从指定源地址 ping 目标矩阵, 判定业务"真的通"
  3. collect_state()    抓取接口/VLAN/LLDP 状态 (验收排障用)

安全原则:
  - 下发前强制备份 (可显式关闭)
  - dry-run 不对设备做任何改动
  - 注释行 (以 ! 或 # 开头) 与生成告警行不会下发到设备
"""
import datetime
import pathlib
import re
from typing import Optional

BACKUP_DIR = pathlib.Path(__file__).parent / "device_backups"

# 厂商 CLI 差异命令表
CMDS = {
    "huawei":  {"backup": "display current-configuration", "save": ("save", "y"),
                "ping": "ping -a {src} -c {n} {dst}", "parse": "loss"},
    "h3c":     {"backup": "display current-configuration", "save": ("save force",),
                "ping": "ping -a {src} -c {n} {dst}", "parse": "loss"},
    "cisco":   {"backup": "show running-config", "save": ("write memory",),
                "ping": "ping {dst} source {src} repeat {n}", "parse": "success"},
    "ruijie":  {"backup": "show running-config", "save": ("write memory",),
                "ping": "ping {dst} source {src} repeat {n}", "parse": "success"},
}


def _cmd_profile(device_type: str) -> dict:
    """device_type -> 厂商命令档 (hp_comware->h3c, 其余前缀匹配)."""
    dt = (device_type or "").lower()
    if "comware" in dt:
        return CMDS["h3c"]
    for key in ("huawei", "cisco", "ruijie"):
        if dt.startswith(key):
            return CMDS[key]
    raise ValueError(f"暂不支持的下发设备类型: {device_type} (支持华为/H3C/思科/锐捷)")


def _clean_commands(commands: list) -> list:
    """过滤注释行和生成告警行 — 这些只给人看, 不下发."""
    return [c.strip() for c in commands
            if c.strip() and not c.strip().startswith(("!", "#"))
            and "WARNING" not in c]


def push_config(host: str, device_type: str, username: str, password: str,
                commands: list, dry_run: bool = True, backup: bool = True,
                port: int = 22) -> dict:
    """连接设备, 备份当前配置, 然后下发 (dry-run 只预览)."""
    from netmiko import ConnectHandler

    profile = _cmd_profile(device_type)
    clean = _clean_commands(commands)
    result = {"host": host, "device_type": device_type, "dry_run": dry_run,
              "command_count": len(clean), "commands": clean, "backup_file": None}

    conn = ConnectHandler(device_type=device_type, host=host, port=port,
                          username=username, password=password, timeout=15)
    try:
        if backup:
            out = conn.send_command(profile["backup"], read_timeout=60)
            BACKUP_DIR.mkdir(exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = BACKUP_DIR / f"{host.replace('.', '_')}_{ts}.cfg"
            path.write_text(out, encoding="utf-8")
            result["backup_file"] = str(path)

        if dry_run:
            result["status"] = "dry-run"
            result["message"] = "仅预览, 未改动设备。确认无误后以 dry_run=false 下发。"
            return result

        output = conn.send_config_set(clean)
        # 保存配置
        save_cmd = profile["save"][0]
        save_out = conn.send_command_timing(save_cmd, delay_factor=2)
        # 华为 save 需要确认 y
        if len(profile["save"]) > 1:
            save_out += conn.send_command_timing(profile["save"][1], delay_factor=2)
        result.update({"status": "success", "output_tail": output[-1500:],
                       "save_output": save_out[-300:]})
        return result
    finally:
        conn.disconnect()


def run_ping_tests(host: str, device_type: str, username: str, password: str,
                   source: str, targets: list, count: int = 5, port: int = 22) -> dict:
    """从设备上以 source 为源地址逐个 ping targets, 返回通过矩阵.
    targets: [{name, ip}, ...]"""
    from netmiko import ConnectHandler

    profile = _cmd_profile(device_type)
    results = []
    conn = ConnectHandler(device_type=device_type, host=host, port=port,
                          username=username, password=password, timeout=15)
    try:
        for tg in targets:
            dst, name = tg.get("ip"), tg.get("name", tg.get("ip"))
            cmd = profile["ping"].format(src=source, dst=dst, n=count)
            out = conn.send_command(cmd, read_timeout=60)
            ok, note = _parse_ping(out, profile["parse"])
            results.append({"name": name, "ip": dst, "command": cmd,
                            "pass": ok, "detail": note})
    finally:
        conn.disconnect()

    passed = sum(1 for r in results if r["pass"])
    return {"host": host, "source": source, "total": len(results),
            "passed": passed, "all_pass": passed == len(results), "results": results}


def collect_state(host: str, device_type: str, username: str, password: str,
                  port: int = 22) -> dict:
    """抓取接口/VLAN/邻居状态, 存 reports 供排障."""
    from netmiko import ConnectHandler

    dt = (device_type or "").lower()
    if "comware" in dt:
        cmds = ["display interface brief", "display vlan brief", "display lldp neighbor-list"]
    elif dt.startswith("cisco") or dt.startswith("ruijie"):
        cmds = ["show ip interface brief", "show vlan brief", "show cdp neighbors"]
    else:
        cmds = ["display ip interface brief", "display vlan", "display lldp neighbor brief"]

    conn = ConnectHandler(device_type=device_type, host=host, port=port,
                          username=username, password=password, timeout=15)
    try:
        out = {}
        for c in cmds:
            out[c] = conn.send_command(c, read_timeout=60)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = BACKUP_DIR / f"state_{host.replace('.', '_')}_{ts}.md"
        BACKUP_DIR.mkdir(exist_ok=True)
        path.write_text("\n\n".join(f"## {k}\n```\n{v}\n```" for k, v in out.items()),
                        encoding="utf-8")
        return {"host": host, "status": "success", "file": str(path), "state": out}
    finally:
        conn.disconnect()


def _parse_ping(out: str, mode: str):
    """解析 ping 输出. mode: loss(丢包率) / success(成功率)."""
    if mode == "loss":
        m = re.search(r"(\d+(?:\.\d+)?)% packet loss", out)
        if not m:
            return False, "无法解析 ping 输出"
        loss = float(m.group(1))
        return loss == 0, f"丢包率 {loss}%"
    else:
        m = re.search(r"Success rate is (\d+) percent", out)
        if not m:
            return False, "无法解析 ping 输出"
        rate = float(m.group(1))
        return rate == 100, f"成功率 {rate}%"


# 一键巡检: 各厂商采集命令 (CPU / 内存 / 版本 / 接口概览)
INSPECT_CMDS = {
    "huawei": ["display cpu-usage", "display memory-usage", "display version", "display ip interface brief"],
    "h3c":    ["display cpu-usage", "display memory", "display version", "display interface brief"],
    "cisco":  ["show processes cpu | include CPU", "show memory statistics", "show version", "show ip interface brief"],
    "ruijie": ["show processes cpu | include CPU", "show memory statistics", "show version", "show ip interface brief"],
}


def inspect_device(host: str, device_type: str, username: str, password: str,
                   port: int = 22) -> dict:
    """一键巡检: 采集 CPU/内存/版本/接口概览, 解析出关键指标供表格展示."""
    from netmiko import ConnectHandler

    dt = (device_type or "").lower()
    if "comware" in dt:
        cmds = INSPECT_CMDS["h3c"]
    elif dt.startswith("cisco") or dt.startswith("ruijie"):
        cmds = INSPECT_CMDS["cisco"]
    else:
        cmds = INSPECT_CMDS["huawei"]

    conn = ConnectHandler(device_type=device_type, host=host, port=port,
                          username=username, password=password, timeout=15)
    try:
        outputs = {}
        for c in cmds:
            try:
                outputs[c] = conn.send_command(c, read_timeout=60)
            except Exception as e:
                outputs[c] = f"(采集失败: {e})"
    finally:
        conn.disconnect()

    blob = "\n".join(outputs.values())

    # CPU: 华为/H3C/思科通用格式 "five seconds: X%" / "five seconds: X%"
    cpu = None
    m = re.search(r"five seconds[:：]?\s*(\d+)(?::\s*\d+)?%", blob, re.I)
    if not m:
        m = re.search(r"cpu[^\d]{0,20}(\d+)%", blob, re.I)
    if m:
        cpu = float(m.group(1))

    # 内存: 华为 "Memory Using Percentage Is: 32%" / H3C "Memory Using Percentage: 32%"
    mem = None
    m = re.search(r"memory[^\d]{0,30}(\d+(?:\.\d+)?)\s*%", blob, re.I)
    if m:
        mem = float(m.group(1))

    # 版本: 取版本输出里的关键行
    version = ""
    ver_out = next((v for k, v in outputs.items() if "version" in k.lower()), "")
    for line in ver_out.splitlines():
        s = line.strip()
        if re.search(r"(version|uptime|with \d+ byte)", s, re.I) and len(s) > 8:
            version = s[:90]
            break
        if s and not version and re.search(r"^[A-Za-z]", s):
            version = s[:90]
            if "version" in s.lower():
                break

    return {"host": host, "device_type": device_type, "status": "success",
            "cpu": cpu, "mem": mem, "version": version,
            "outputs": outputs,
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
