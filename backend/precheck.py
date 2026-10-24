#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
precheck.py — 下发前安全预检 (纯文本分析, 不连接设备)
  1. escape_risks()    逃生口检测: 扫描即将下发的命令, 标记可能自断管理通道的配置
  2. change_summary()  变更摘要: 按类别聚合统计, 一屏看清这次改动动了什么
"""


def _clean(commands):
    return [c.strip() for c in (commands or [])
            if c and c.strip() and not c.strip().startswith(("!", "#"))
            and "WARNING" not in c]


# 无上下文即可判定的危险命令模式 (已小写匹配)
_ESCAPE_PATTERNS = [
    # (匹配函数, 级别, 原因)
    (lambda c: c.startswith(("undo ssh", "undo stelnet", "undo sftp", "no ip ssh")), "danger",
     "关闭 SSH 服务 — 真实下发后平台将无法再连接此设备 (Console 口除外)"),
    (lambda c: c.startswith(("undo telnet", "no ip telnet")), "warn",
     "关闭 Telnet 服务 — 若 SSH 未配置好将失去远程管理手段"),
    (lambda c: c.startswith(("undo user-interface", "no line vty", "no line con")), "danger",
     "修改/删除 VTY(或 Console) 用户界面 — 可能中断远程登录能力"),
    (lambda c: c.startswith(("undo local-user", "no username", "undo local-aaa-user")), "danger",
     "删除本地用户 — 若删的是当前登录账号将直接失联"),
    (lambda c: c.startswith(("undo aaa authentication", "undo aaa authorization", "no aaa new-model")), "warn",
     "改动 AAA 认证框架 — 认证策略变化可能导致登录被拒"),
    (lambda c: c.startswith(("undo ip route-static 0.0.0.0", "no ip route 0.0.0.0", "no ip route static 0.0.0.0")), "warn",
     "删除默认路由 — 设备将失去去往管理网段/外网的路径"),
    (lambda c: c.startswith(("undo interface vlanif", "no interface vlan", "undo interface vlan")), "danger",
     "删除 VLANIF 接口 — 若为管理 VLANIF 将直接失联"),
]


def escape_risks(commands: list) -> list:
    """逃生口检测: 返回 [{command, level, reason}], level: danger/warn."""
    clean = _clean(commands)
    risks, seen = [], set()
    current_if = ""
    for c in clean:
        low = c.lower()
        # 记录当前 interface 上下文 (用于 shutdown / ip address 判定)
        if low.startswith(("interface ", "int ")):
            current_if = c
        elif not low.startswith((" ", "\t")) and low and not low.startswith(("interface", "int ")):
            # 回到非接口上下文的判定交给前缀匹配, 这里仅跟踪接口名
            pass
        for match, level, reason in _ESCAPE_PATTERNS:
            if match(low) and c not in seen:
                risks.append({"command": c, "level": level, "reason": reason})
                seen.add(c)
                break
        else:
            # 上下文相关判定
            if low == "shutdown" and current_if:
                ifl = current_if.lower()
                if "vlanif" in ifl or "loopback" in ifl or "mgmt" in ifl or "management" in ifl:
                    risks.append({"command": f"{current_if} → shutdown", "level": "danger",
                                  "reason": "关闭管理接口 (VLANIF/Loopback/管理口) — 将直接中断远程管理通道"})
                    seen.add(c)
                else:
                    risks.append({"command": f"{current_if} → shutdown", "level": "warn",
                                  "reason": "关闭物理接口 — 请确认不影响上联管理链路"})
                    seen.add(c)
    return risks


# 变更摘要分类 (顺序即优先级, 命中即归类)
_SUMMARY_RULES = [
    ("VLAN", lambda c: c.startswith(("vlan ", "vlan-batch", "undo vlan"))),
    ("路由", lambda c: any(k in c for k in ("route-static", "ip route", "router ospf", "ospf ", "ip routing"))),
    ("安全/AAA", lambda c: any(k in c for k in ("acl", "ssh", "stelnet", "telnet", "aaa", "local-user",
                                                "user-interface", "radius", "hwtacacs", "portal"))),
    ("DHCP", lambda c: "dhcp" in c),
    ("管理协议", lambda c: any(k in c for k in ("ntp", "snmp", "sysname", "hostname", "dns", "lldp", "logging", "info-center"))),
    ("接口", lambda c: c.startswith(("interface", "int ", "port ", "switchport", "undo port", "eth-trunk",
                                     "port-group", "channel-group", "shutdown", "undo shutdown"))),
]


def change_summary(commands: list) -> dict:
    """变更摘要: {类别: 条数}, 兜底归入 其他."""
    clean = _clean(commands)
    summary = {}
    for c in clean:
        low = c.lower()
        for name, rule in _SUMMARY_RULES:
            if rule(low):
                summary[name] = summary.get(name, 0) + 1
                break
        else:
            summary["其他"] = summary.get("其他", 0) + 1
    return summary
