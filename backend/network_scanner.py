#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
network_scanner.py — 企业网络自动发现引擎
从一台种子设备 SSH 登录, 通过 LLDP/CDP 邻居表递归发现整网设备,
输出结构化拓扑 (与 AI 识图同格式, 可直接渲染到画布) + 网络诊断报告。

发现原理:
  1. SSH 登录种子设备 (netmiko, 支持华为/H3C/思科/锐捷)
  2. 采集 LLDP/CDP 详细邻居表 (含对端管理地址/系统名/端口)
  3. 对每个新发现的管理地址递归登录, BFS 直到最大跳数
  4. 无法登录的设备仍保留节点 (信息来自邻居表), 并记入诊断
"""
import datetime
import re

# netmiko device_type 映射
NETMIKO_TYPE = {
    "huawei": "huawei",
    "h3c": "hp_comware",
    "cisco": "cisco_ios",
    "ruijie": "ruijie_os",
}

# 逐个尝试的邻居表命令 (首个返回可解析结果的生效)
NEIGHBOR_CMDS = {
    "huawei": ["display lldp neighbor", "display lldp neighbor brief"],
    "h3c": ["display lldp neighbor-information verbose", "display lldp neighbor verbose",
            "display lldp neighbor-list"],
    "cisco": ["show cdp neighbors detail", "show lldp neighbors detail"],
    "ruijie": ["show cdp neighbors detail", "show lldp neighbors detail"],
}
VERSION_CMD = {
    "huawei": "display version", "h3c": "display version",
    "cisco": "show version", "ruijie": "show version",
}


def _run(conn, commands):
    """逐条执行命令, 返回首个非空输出 (跳过报错)."""
    for c in commands:
        try:
            out = conn.send_command(c, read_timeout=60)
            if out and "Invalid" not in out and "Unrecognized" not in out and "% " not in out[:5]:
                return c, out
        except Exception:
            continue
    return None, ""


def _guess_vendor(version_text, default):
    t = version_text or ""
    if "Versatile Routing Platform" in t or "HUAWEI" in t.upper():
        return "huawei"
    if "Comware" in t:
        return "h3c"
    if "Cisco IOS" in t or "Cisco Internetwork" in t:
        return "cisco"
    if "RGOS" in t or "Ruijie" in t:
        return "ruijie"
    return default


def _parse_model(vendor, version_text):
    t = version_text or ""
    if vendor == "cisco":
        m = re.search(r"cisco\s+([\w-]+)", t)
        if m:
            return m.group(1)
    m = re.search(r"(H3C\s+)?([SCEANR]\d{4}[\w-]*)", t)
    if m:
        return m.group(2)
    m = re.search(r"(Huawei\s+)?([\w-]+\s*uptime)", t)
    if m:
        return m.group(2).replace(" uptime", "").strip()
    return ""


def _classify(name, model):
    """按主机名/型号推断节点类别与角色."""
    text = f"{name} {model}".upper()
    if re.search(r"FW|USG|FIREWALL|防火墙|ASA|PIX", text):
        return "firewall", "security"
    if re.search(r"AR\d{2,4}|NE\d{2}|RT[-_]|路由器", text):
        return "router", "router"
    if re.search(r"\bAP|AIR-|无线接入", text):
        return "ap", "wireless"
    if re.search(r"\bAC\d|WLAN|无线控制", text):
        return "ac", "wireless"
    if re.search(r"SRV|SERVER|服务器|ESXI|VM", text):
        return "server", "endpoint"
    if re.search(r"核心|CORE|S12\d{3}|CE\d{4}", text):
        return "switch", "core"
    if re.search(r"汇聚|AGG", text):
        return "switch", "access"
    return "switch", "access"


# ---------------- 邻居表解析 ----------------

def _parse_cisco_detail(text):
    """show cdp neighbors detail: '---' 分块."""
    out = []
    for block in re.split(r"-{5,}", text):
        dev = re.search(r"Device ID\s*:?\s*(\S+)", block)
        ip = re.search(r"IP(?:v4)? address\s*:?\s*(\d+\.\d+\.\d+\.\d+)", block)
        local = re.search(r"Interface\s*:\s*([\w/]+)", block)
        port = re.search(r"Port ID(?:\s*\(outgoing port\))?\s*:\s*([\w/]+)", block)
        plat = re.search(r"Platform\s*:\s*(.+)", block)
        if dev and local:
            out.append({
                "local_port": local.group(1),
                "name": dev.group(1).split(".")[0],
                "mgmt_ip": ip.group(1) if ip else "",
                "remote_port": port.group(1) if port else "",
                "model": plat.group(1).strip() if plat else "",
            })
    return out


def _parse_huawei_lldp(text):
    """display lldp neighbor: 'xxx has N neighbor(s):' 分块."""
    out = []
    cur_local = None
    for line in text.splitlines():
        m = re.match(r"^(\S+)\s+has\s+\d+\s+neighbo", line)
        if m:
            cur_local = m.group(1)
            continue
        if not cur_local:
            continue
        name = re.search(r"System name\s*[:：]\s*(\S+)", line)
        ip = re.search(r"Management address\s*[:：]\s*(\d+\.\d+\.\d+\.\d+)", line)
        port = re.search(r"Port ID\s*[:：]\s*([\w/.:-]+)", line)
        if name:
            out.append({"local_port": cur_local, "name": name.group(1),
                        "mgmt_ip": ip.group(1) if ip else "",
                        "remote_port": port.group(1) if port else "", "model": ""})
            cur_local = None
    return out


def _parse_h3c_verbose(text):
    """display lldp neighbor-information verbose: Local interface 分块."""
    out = []
    cur = {}
    for line in text.splitlines():
        m_local = re.search(r"(?:Local|Neighbor) interface\s*[:：]\s*([\w/]+)", line)
        if m_local:
            if cur.get("name"):
                out.append(cur)
            cur = {"local_port": m_local.group(1), "name": "", "mgmt_ip": "",
                   "remote_port": "", "model": ""}
            continue
        name = re.search(r"System name\s*[:：]\s*(\S+)", line)
        ip = re.search(r"Management address\s*[:：]\s*(\d+\.\d+\.\d+\.\d+)", line)
        port = re.search(r"Port ID\s*[:：]\s*([\w/.:-]+)", line)
        if cur:
            if name and not cur["name"]:
                cur["name"] = name.group(1)
            if ip and not cur["mgmt_ip"]:
                cur["mgmt_ip"] = ip.group(1)
            if port and not cur["remote_port"]:
                cur["remote_port"] = port.group(1)
    if cur.get("name"):
        out.append(cur)
    return out


def _parse_brief(text, vendor):
    """brief 表 (无管理地址): '本地端口 对端MAC/名 对端端口' 行式."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and re.match(r"^(GE|ETH|TEN|XGE|Fa|Gi|Te|Eth|Ten)", parts[0], re.I):
            if vendor == "huawei":
                out.append({"local_port": parts[0], "name": parts[2],
                            "mgmt_ip": "", "remote_port": parts[3] if len(parts) > 3 else "",
                            "model": ""})
    return out


def parse_neighbors(vendor, cmd, text):
    if "detail" in cmd or "verbose" in cmd:
        if vendor in ("cisco", "ruijie"):
            return _parse_cisco_detail(text)
        if vendor == "huawei":
            return _parse_huawei_lldp(text)
        return _parse_h3c_verbose(text)
    return _parse_brief(text, vendor)


# ---------------- 采集单台设备 ----------------

def _collect_device(host, vendor, username, password, ssh_port, progress=None):
    """登录单台设备, 返回 {ok, name, model, vendor, neighbors, error}."""
    try:
        from netmiko import ConnectHandler
    except ImportError:
        raise RuntimeError("后端缺少 netmiko, 请先 pip install netmiko")
    dt = NETMIKO_TYPE.get(vendor, "huawei")
    result = {"host": host, "ok": False, "name": host, "model": "", "vendor": vendor,
              "neighbors": [], "error": ""}
    try:
        if progress:
            progress(f"SSH 登录 {host} ...")
        conn = ConnectHandler(device_type=dt, host=host, port=ssh_port,
                              username=username, password=password, timeout=15)
        try:
            _, ver_out = _run(conn, [VERSION_CMD[vendor]])
            vendor = _guess_vendor(ver_out, vendor)
            result["vendor"] = vendor
            result["model"] = _parse_model(vendor, ver_out)
            name_m = re.search(r"(\S+)\s+uptime", ver_out or "")
            result["name"] = name_m.group(1) if name_m else host
            if not result["model"]:
                result["model"] = _parse_model(vendor, ver_out)
            # prompt 兜底主机名
            if result["name"] == host:
                prompt = conn.find_prompt() or ""
                prompt = re.sub(r"[<>#]", "", prompt).strip()
                if prompt:
                    result["name"] = prompt
            cmd, out = _run(conn, NEIGHBOR_CMDS[vendor])
            if out:
                result["neighbors"] = parse_neighbors(vendor, cmd, out)
            result["ok"] = True
        finally:
            conn.disconnect()
    except Exception as e:
        result["error"] = str(e).split("\n")[0][:200]
    return result


# ---------------- 递归发现 ----------------

def discover_network(seed_ip, username, password, vendor="huawei",
                     max_depth=3, ssh_port=22, progress=None):
    """BFS 发现整网. 返回 {topology, diagnostics, stats} (topology 与 AI 识图同构)."""
    visited = {}          # ip -> node dict
    queue = [(seed_ip, 0)]
    links = []
    seen_edges = set()
    diagnostics = []

    while queue:
        ip, depth = queue.pop(0)
        if ip in visited:
            continue
        info = _collect_device(ip, vendor, username, password, ssh_port, progress)
        if progress:
            n = len(info.get("neighbors", []))
            progress(f"{'✓' if info['ok'] else '✗'} {info['name']} ({ip}) 邻居 {n} 台")

        cat, role = _classify(info["name"], info["model"])
        node = {
            "label": info["name"],
            "category": cat,
            "role": role,
            "vendor": {"huawei": "Huawei", "h3c": "H3C", "cisco": "Cisco",
                       "ruijie": "Ruijie"}.get(info["vendor"], "unknown"),
            "model": info["model"] or "unknown",
            "mgmtIp": ip,
            "description": f"自动发现 (跳数 {depth})" if info["ok"]
                           else f"自动发现; SSH 采集失败: {info['error']}",
        }
        visited[ip] = node

        if not info["ok"]:
            diagnostics.append({
                "level": "error",
                "device": info["name"],
                "ip": ip,
                "message": f"SSH 登录失败: {info['error']} — 无法采集其邻居, 拓扑可能在 此处截断",
            })
            continue

        for nb in info["neighbors"]:
            key = (info["name"], nb["name"])
            if key in seen_edges or key[::-1] in seen_edges:
                continue
            seen_edges.add(key)
            links.append({
                "from": info["name"], "to": nb["name"],
                "fromPort": nb.get("local_port", ""),
                "toPort": nb.get("remote_port", ""),
                "mode": "trunk" if not re.search(r"AP|SRV|SERVER|PC", nb["name"].upper()) else "access",
                "linkLabel": "LLDP 发现" if not nb.get("remote_port")
                             else f"{nb.get('local_port','')} ↔ {nb.get('remote_port','')}",
            })
            # 找到管理地址且未访问 → 入队
            if nb.get("mgmt_ip") and nb["mgmt_ip"] not in visited and depth + 1 <= max_depth:
                queue.append((nb["mgmt_ip"], depth + 1))
            elif not nb.get("mgmt_ip") and nb["name"] not in {v["label"] for v in visited.values()}:
                # 无管理地址: 保留节点但无法深入
                pseudo_key = f"nb_{nb['name']}"
                if pseudo_key not in visited:
                    cat2, role2 = _classify(nb["name"], nb.get("model", ""))
                    visited[pseudo_key] = {
                        "label": nb["name"], "category": cat2, "role": role2,
                        "vendor": "unknown", "model": nb.get("model", "unknown"),
                        "mgmtIp": "", "description": "自动发现 (仅邻居表信息, 未能登录采集)",
                    }
                    diagnostics.append({
                        "level": "warning", "device": nb["name"], "ip": "-",
                        "message": "邻居表中无管理地址, 未能递归采集 — 建议检查 LLDP 管理地址配置 (lldp management-address)",
                    })

    # 节点补 key: 用 label 做拓扑 key (links 用的就是 name)
    nodes = {label: node for label, node in visited.items()}
    # 修正 links 里的 from/to 映射 (mgmt 采集设备的 key 是其 label)
    label_of_ip = {ip: n["label"] for ip, n in visited.items()}
    final_links = []
    for lk in links:
        f = label_of_ip.get(lk["from"], lk["from"])
        t = label_of_ip.get(lk["to"], lk["to"])
        final_links.append({**lk, "from": f, "to": t})

    # 诊断: 孤点 / 单链路
    degree = {}
    for lk in final_links:
        degree[lk["from"]] = degree.get(lk["from"], 0) + 1
        degree[lk["to"]] = degree.get(lk["to"], 0) + 1
    for label, node in nodes.items():
        d = degree.get(label, 0)
        if d == 0:
            diagnostics.append({"level": "warning", "device": label, "ip": node.get("mgmtIp", ""),
                                "message": "未发现任何邻居链路 — 可能是终端设备, 或 LLDP/CDP 未启用"})
        elif d == 1 and node["role"] in ("core", "access"):
            diagnostics.append({"level": "warning", "device": label, "ip": node.get("mgmtIp", ""),
                                "message": "交换设备仅有一条上联链路 — 存在单点故障风险, 建议确认是否需要双上联"})

    names = {}
    for label, node in nodes.items():
        names.setdefault(label.lower(), []).append(label)
    for low, labels in names.items():
        if len(labels) > 1:
            diagnostics.append({"level": "warning", "device": labels[0], "ip": "-",
                                "message": f"发现重名设备: {', '.join(labels)} — 主机名重复, 建议按规范改名"})

    return {
        "topology": {
            "nodes": {k: nodes[k] for k in sorted(nodes)},
            "links": final_links,
        },
        "diagnostics": diagnostics,
        "stats": {
            "devices": len(nodes),
            "links": len(final_links),
            "scanned": sum(1 for n in nodes.values() if "SSH 采集失败" not in n["description"]),
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


# ---------------- 演示模式 (无真实网络可预览) ----------------

def demo_scan(progress=None):
    """返回一套固定的商场园区网发现结果, 用于演示/验证 UI."""
    if progress:
        for msg in ["SSH 登录 10.94.89.1 ...", "✓ HX-JR-SW01 (10.94.89.1) 邻居 6 台",
                    "✓ HX-XF-SW01 (10.94.89.2) 邻居 4 台",
                    "✗ HJ-JR-SW03 (10.94.90.13) SSH 登录失败: timeout",
                    "✓ HJ-SY-SW01 (10.94.90.21) 邻居 3 台"]:
            progress(msg)
    topo = {
        "nodes": {
            "HX-JR-SW01": {"label": "HX-JR-SW01", "category": "switch", "role": "core",
                           "vendor": "Huawei", "model": "S12700E-8", "mgmtIp": "10.94.89.1",
                           "description": "自动发现 (跳数 0)"},
            "HX-XF-SW01": {"label": "HX-XF-SW01", "category": "switch", "role": "core",
                           "vendor": "Huawei", "model": "S12700E-8", "mgmtIp": "10.94.89.2",
                           "description": "自动发现 (跳数 0)"},
            "FW-YW-01": {"label": "FW-YW-01", "category": "firewall", "role": "security",
                         "vendor": "Huawei", "model": "USG6000E", "mgmtIp": "10.94.89.246",
                         "description": "自动发现 (跳数 1)"},
            "HJ-JR-SW01": {"label": "HJ-JR-SW01", "category": "switch", "role": "access",
                           "vendor": "Huawei", "model": "S5735-L24T4S-A", "mgmtIp": "10.94.90.11",
                           "description": "自动发现 (跳数 1)"},
            "HJ-JR-SW02": {"label": "HJ-JR-SW02", "category": "switch", "role": "access",
                           "vendor": "Huawei", "model": "S5735-L24T4S-A", "mgmtIp": "10.94.90.12",
                           "description": "自动发现 (跳数 1)"},
            "HJ-JR-SW03": {"label": "HJ-JR-SW03", "category": "switch", "role": "access",
                           "vendor": "Huawei", "model": "S5735-L24T4S-A", "mgmtIp": "10.94.90.13",
                           "description": "自动发现; SSH 采集失败: timeout — 拓扑可能在此处截断"},
            "HJ-SY-SW01": {"label": "HJ-SY-SW01", "category": "switch", "role": "access",
                           "vendor": "Huawei", "model": "S5735-L48T4X-A1", "mgmtIp": "10.94.90.21",
                           "description": "自动发现 (跳数 1)"},
            "AC-YW-01": {"label": "AC-YW-01", "category": "ac", "role": "wireless",
                         "vendor": "Huawei", "model": "AC6605", "mgmtIp": "10.94.90.31",
                         "description": "自动发现 (跳数 1)"},
            "AP-SY-0F01": {"label": "AP-SY-0F01", "category": "ap", "role": "wireless",
                           "vendor": "Huawei", "model": "AirEngine5760", "mgmtIp": "",
                           "description": "自动发现 (仅邻居表信息, 未能登录采集)"},
            "SRV-QY-01": {"label": "SRV-QY-01", "category": "server", "role": "endpoint",
                          "vendor": "unknown", "model": "unknown", "mgmtIp": "",
                          "description": "自动发现 (仅邻居表信息, 未能登录采集)"},
        },
        "links": [
            {"from": "FW-YW-01", "to": "HX-JR-SW01", "fromPort": "GE1/0/0", "toPort": "GE1/0/1",
             "mode": "trunk", "linkLabel": "GE1/0/0 ↔ GE1/0/1"},
            {"from": "HX-JR-SW01", "to": "HX-XF-SW01", "fromPort": "GE1/0/3", "toPort": "GE1/0/3",
             "mode": "trunk", "linkLabel": "GE1/0/3 ↔ GE1/0/3"},
            {"from": "HX-JR-SW01", "to": "HJ-JR-SW01", "fromPort": "GE1/0/10", "toPort": "GE0/0/24",
             "mode": "trunk", "linkLabel": "GE1/0/10 ↔ GE0/0/24"},
            {"from": "HX-JR-SW01", "to": "HJ-JR-SW02", "fromPort": "GE1/0/11", "toPort": "GE0/0/24",
             "mode": "trunk", "linkLabel": "GE1/0/11 ↔ GE0/0/24"},
            {"from": "HX-JR-SW01", "to": "HJ-JR-SW03", "fromPort": "GE1/0/12", "toPort": "GE0/0/24",
             "mode": "trunk", "linkLabel": "GE1/0/12 ↔ GE0/0/24"},
            {"from": "HX-XF-SW01", "to": "HJ-SY-SW01", "fromPort": "GE1/0/10", "toPort": "GE0/0/48",
             "mode": "trunk", "linkLabel": "GE1/0/10 ↔ GE0/0/48"},
            {"from": "HX-XF-SW01", "to": "AC-YW-01", "fromPort": "GE1/0/20", "toPort": "GE0/0/1",
             "mode": "trunk", "linkLabel": "GE1/0/20 ↔ GE0/0/1"},
            {"from": "AC-YW-01", "to": "AP-SY-0F01", "fromPort": "GE0/0/8", "toPort": "ETH0",
             "mode": "access", "linkLabel": "GE0/0/8 ↔ ETH0"},
            {"from": "HX-XF-SW01", "to": "SRV-QY-01", "fromPort": "GE1/0/24", "toPort": "ETH0",
             "mode": "access", "linkLabel": "GE1/0/24 ↔ ETH0"},
        ],
    }
    diagnostics = [
        {"level": "error", "device": "HJ-JR-SW03", "ip": "10.94.90.13",
         "message": "SSH 登录失败: timeout — 无法采集其邻居, 拓扑可能在此处截断 (检查管理网段路由/账号权限)"},
        {"level": "warning", "device": "HJ-JR-SW03", "ip": "10.94.90.13",
         "message": "交换设备仅有一条上联链路 — 存在单点故障风险, 建议确认是否需要双上联"},
        {"level": "warning", "device": "AP-SY-0F01", "ip": "-",
         "message": "邻居表中无管理地址, 未能递归采集 — 建议检查 LLDP 管理地址配置 (lldp management-address)"},
        {"level": "info", "device": "全网", "ip": "-",
         "message": "已发现 10 台设备 / 9 条链路; 建议在核心设备开启 lldp 与统一主机名规范"},
    ]
    stats = {"devices": 10, "links": 9, "scanned": 7,
             "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    return {"topology": topo, "diagnostics": diagnostics, "stats": stats}
