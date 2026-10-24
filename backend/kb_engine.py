"""Knowledge Base Engine — fuzzy search, template matching, variable substitution."""
import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, List, Set

KB_DIR = Path(__file__).parent / "knowledge_base"
COMMANDS_DIR = KB_DIR / "commands"

# ---- 生成告警机制 ----
# 生成过程中发现的"不可信输出"(厂商回退/语法缺键/模板缺失)统一记录到这里,
# 并以注释行形式注入到对应设备的配置里, 让用户在 UI 上直接看到。
_GEN_WARNINGS: Dict[str, List[str]] = {}  # node_key -> [warning, ...]


def _warn(node_key: str, msg: str) -> None:
    """记录一条针对某设备的生成告警."""
    _GEN_WARNINGS.setdefault(node_key, []).append(msg)


def _warn_lines(node_key: str, comment_char: str = "!") -> list:
    """把该设备积累的告警转成配置注释行 (放配置开头, 最显眼)."""
    warns = _GEN_WARNINGS.get(node_key) or []
    if not warns:
        return []
    out = [f"{comment_char} ===== 生成告警: 本配置含 {len(warns)} 处不可信内容, 请人工核对 ====="]
    for w in warns:
        out.append(f"{comment_char} WARNING: {w}")
    out.append(f"{comment_char} ============================================")
    return out


def _comment_char(vendor_key: str) -> str:
    """不同厂商 CLI 的注释/无害行前缀."""
    return "#" if vendor_key in ("Huawei", "H3C", "Maipu", "Ruijie", "ZTE", "Fiberhome", "Raisecom", "Dcn", "Inspur", "Boda", "Hikvision", "Tplink", "Dptecn") else "!"


def _fmt(template: str, ctx: dict) -> Optional[str]:
    """安全格式化: 模板占位符与上下文完全匹配才返回结果, 否则 None (由调用方决定如何告警)."""
    try:
        return template.format(**ctx)
    except (KeyError, ValueError):
        return None


def _vlan_ctx(v: int, gw: str, mask: str, prefix: int) -> dict:
    """构造 VLAN 相关模板的完整格式化上下文.
    覆盖各家语法表可能用到的全部占位符: {vlan} {vlan_name} {ip} {mask} {prefix}
    {net} {pool_name} {gw} {dns} {start} {end} {server_ip} {vlans}"""
    return {
        "vlan": v, "vlan_name": f"VLAN{v}",
        "ip": gw, "mask": mask, "prefix": prefix,
        "net": _mask_to_net(gw, mask), "pool_name": f"vlan{v}",
        "gw": gw, "dns": gw, "start": gw, "end": gw, "server_ip": gw,
        "vlans": str(v),
    }


def _mask_to_net(ip: str, mask: str) -> str:
    """由 IP + 掩码推出网段地址, 如 192.168.10.1/24 -> 192.168.10.0"""
    try:
        import ipaddress
        iface = ipaddress.ip_interface(f"{ip}/{_mask_to_prefix(mask)}")
        return str(iface.network.network_address)
    except ValueError:
        return ip


def _mask_to_prefix(mask: str) -> int:
    """255.255.255.0 -> 24; 兼容 '24' 形式."""
    mask = str(mask).strip()
    if mask.isdigit():
        return int(mask)
    try:
        import ipaddress
        return bin(int(ipaddress.IPv4Address(mask))).count("1")
    except ValueError:
        return 24

# ---- Loaders ----

def load_index():
    with open(KB_DIR / "index.json", "r", encoding="utf-8") as f:
        return json.load(f)

def load_vendor(vendor: str) -> Optional[Dict]:
    """Load a vendor command file. Returns None if not found."""
    path = COMMANDS_DIR / f"{vendor.lower()}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def list_vendors() -> List[str]:
    """List all available vendor names."""
    vendors = []
    for f in sorted(COMMANDS_DIR.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                vendors.append(data["vendor"])
        except Exception:
            continue
    return vendors

# ---- Fuzzy matching ----

def _tokenize(text: str) -> Set[str]:
    """Break text into lowercase tokens for fuzzy matching."""
    tokens = set()
    # Split on non-alphanumeric characters (handles Chinese + English)
    for part in re.split(r'[\s,，。/、；;：:（）\(\)\[\]【】\-_=+]+', text.lower()):
        part = part.strip()
        if part:
            tokens.add(part)
    return tokens

def _match_score(query: str, target: str, keywords: List[str]) -> float:
    """Calculate relevance score between query and target. Higher = better match."""
    q_lower = query.lower().strip()
    target_lower = target.lower()

    # Exact match in name/title (highest priority)
    if q_lower == target_lower:
        return 100.0

    # Query fully contained in target
    if q_lower in target_lower:
        return 80.0

    # Query tokens match keywords
    q_tokens = _tokenize(q_lower)
    if not q_tokens:
        return 0.0

    kw_lower = [k.lower() for k in keywords]
    kw_text = " ".join(kw_lower)
    hits = sum(1 for t in q_tokens if t in kw_text or any(t in k for k in kw_lower))

    # Token coverage in target
    target_tokens = _tokenize(target_lower)
    target_hits = sum(1 for t in q_tokens if any(t in tt for tt in target_tokens))

    # Partial substring match bonus
    partial_bonus = 5.0 if any(qt in target_lower for qt in q_tokens if len(qt) >= 2) else 0.0

    return hits * 15.0 + target_hits * 10.0 + partial_bonus

# ---- Search API ----

def search(query: str = "", vendor: str = "all", category: str = "all", limit: int = 30) -> Dict:
    """Main search function. Returns matched articles and commands."""
    index = load_index()
    results = {"articles": [], "commands": [], "total": 0}

    # --- Search networking basics articles ---
    for article in index.get("networking_basics", []):
        score = _match_score(query, article["title"], article.get("keywords", []))
        if query:
            # Also search in content
            content_score = _match_score(query, article.get("content", ""), [])
            score = max(score, content_score * 0.6)
        if not query or score > 5:
            results["articles"].append({
                "id": article["id"],
                "title": article["title"],
                "content": article["content"],
                "keywords": article.get("keywords", []),
                "score": round(score, 1),
                "type": "article",
            })

    # Sort by score descending
    results["articles"].sort(key=lambda a: a["score"], reverse=True)
    if limit:
        results["articles"] = results["articles"][:limit]

    # --- Search tutorials ---
    for tut in index.get("tutorials", []):
        score = _match_score(query, tut["title"], tut.get("keywords", []))
        if query:
            content_score = _match_score(query, tut.get("content", ""), [])
            score = max(score, content_score * 0.6)
        if not query or score > 5:
            results["articles"].append({
                "id": tut["id"],
                "title": "【教程】" + tut["title"],
                "content": tut["content"],
                "keywords": tut.get("keywords", []),
                "score": round(score, 1),
                "type": "tutorial",
            })

    # Re-sort
    results["articles"].sort(key=lambda a: a["score"], reverse=True)
    if limit:
        results["articles"] = results["articles"][:limit]

    # --- Search vendor commands ---
    vendor_list = list_vendors() if vendor == "all" else [v for v in [vendor] if v]
    for v in vendor_list:
        vdata = load_vendor(v)
        if not vdata:
            continue
        vname = vdata["vendor"]
        cats = vdata.get("categories", {})

        # If category filter specified, only search that category
        cat_items = [(category, cats[category])] if category != "all" and category in cats else cats.items()

        for cat_id, cat_data in cat_items:
            for cmd in cat_data.get("commands", []):
                score = _match_score(query, cmd["name"], cat_data.get("keywords", []) + cmd.get("keywords", []))
                # Also match in syntax
                syntax_score = _match_score(query, cmd.get("syntax", ""), [])
                score = max(score, syntax_score * 0.7)
                # Also match in description
                desc_score = _match_score(query, cmd.get("description", ""), [])
                score = max(score, desc_score * 0.5)

                if not query or score > 3:
                    results["commands"].append({
                        "vendor": vname,
                        "category": cat_id,
                        "categoryName": cat_data["name"],
                        "name": cmd["name"],
                        "syntax": cmd.get("syntax", ""),
                        "example": cmd.get("example", ""),
                        "description": cmd.get("description", ""),
                        "mode": cmd.get("mode", ""),
                        "score": round(score, 1),
                        "type": "command",
                    })

    results["commands"].sort(key=lambda c: c["score"], reverse=True)
    if limit:
        results["commands"] = results["commands"][:limit]

    results["total"] = len(results["articles"]) + len(results["commands"])
    return results

def get_vendor_categories(vendor: str) -> Dict:
    """Get category tree for a specific vendor."""
    vdata = load_vendor(vendor)
    if not vdata:
        return {}
    return {
        "vendor": vdata["vendor"],
        "categories": {
            cid: {"name": cdata["name"], "command_count": len(cdata.get("commands", []))}
            for cid, cdata in vdata.get("categories", {}).items()
        }
    }

def get_category_commands(vendor: str, category: str) -> List:
    """Get all commands for a vendor+category."""
    vdata = load_vendor(vendor)
    if not vdata:
        return []
    cat = vdata.get("categories", {}).get(category)
    if not cat:
        return []
    return [{
        "name": cmd["name"],
        "syntax": cmd.get("syntax", ""),
        "example": cmd.get("example", ""),
        "description": cmd.get("description", ""),
        "mode": cmd.get("mode", ""),
    } for cmd in cat.get("commands", [])]


# ---- Template-based config generation (offline) ----

# ---- CLI Command Validation ----

# Commands valid in each mode per vendor style
_CLI_MODE_COMMANDS = {
    "user": {
        "huawei_like": ["display", "ping", "tracert", "telnet", "ssh", "system-view", "reset", "reboot", "dir", "cd", "copy", "delete", "save", "quit"],
        "cisco_like": ["show", "ping", "traceroute", "telnet", "ssh", "configure", "enable", "reload", "dir", "cd", "copy", "delete", "write", "exit"],
    },
    "system": {
        "huawei_like": ["sysname", "vlan", "interface", "stp", "dhcp", "ip", "ospf", "acl", "undo", "quit", "return", "display", "save", "user-interface", "aaa", "lldp"],
        "cisco_like": ["hostname", "vlan", "interface", "spanning-tree", "ip", "router", "access-list", "no", "exit", "end", "show", "do", "line", "username"],
    },
    "interface": {
        "huawei_like": ["ip", "port", "stp", "dhcp", "description", "shutdown", "undo", "quit", "display"],
        "cisco_like": ["ip", "switchport", "spanning-tree", "description", "shutdown", "no", "exit", "end"],
    },
}

def _vendor_style(vendor: str) -> str:
    """Return 'huawei_like' or 'cisco_like' based on vendor."""
    v = vendor.lower()
    if v in ("huawei", "h3c", "maipu", "fiberhome", "juniper", "hpe", "extreme", "sonic"):
        return "huawei_like"
    return "cisco_like"

def validate_cli_command(command: str, vendor: str, mode: str = "user") -> dict:
    """Validate a CLI command against knowledge base and mode context.

    Returns dict with: valid, response, suggested_fix, help_text
    """
    cmd = command.strip()
    if not cmd:
        return {"valid": True, "response": "", "suggested_fix": None, "help_text": None}

    first_word = cmd.split()[0].lower()
    style = _vendor_style(vendor)

    # Check mode compatibility
    mode_cmds = _CLI_MODE_COMMANDS.get(mode, {}).get(style, [])
    if mode_cmds and first_word not in mode_cmds and first_word not in ("?", "help", "clear", "cls"):
        return {
            "valid": False,
            "response": f"当前模式下不支持命令 '{first_word}'",
            "suggested_fix": None,
            "help_text": f"当前模式可用命令: {', '.join(mode_cmds[:15])}...",
        }

    # Search knowledge base for matching command
    results = search(first_word, vendor, "all", limit=5)
    matches = [c for c in results.get("commands", []) if c["name"].lower().startswith(first_word) or first_word in c.get("syntax", "").lower()]

    if matches:
        best = matches[0]
        return {
            "valid": True,
            "response": f"[OK] {best['name']}",
            "suggested_fix": None,
            "help_text": f"语法: {best['syntax']}\n示例: {best.get('example', '')}\n说明: {best.get('description', '')}",
        }

    # Check if it's a known system command
    if first_word in ("?", "help", "clear", "cls"):
        return {"valid": True, "response": "", "suggested_fix": None, "help_text": None}

    return {
        "valid": True,  # Don't block unknown commands — let user experiment
        "response": "命令已接受（未在知识库中找到匹配）",
        "suggested_fix": None,
        "help_text": f"未找到 '{first_word}' 的文档。输入 ? 查看可用命令。",
    }


def validate_cli_batch(commands, vendor: str) -> list:
    """下发前批量 CLI 预检 (面向配置模式命令列表).

    逐条返回 {command, level, message}:
      ok    — 首词属于该厂商语系, 通过
      error — 首词明确属于另一厂商语系 (如华为设备上敲 switchport), 应阻断
      warn  — 知识库未收录, 无法判定, 提示人工确认
    """
    style = _vendor_style(vendor)
    other = "cisco_like" if style == "huawei_like" else "huawei_like"
    allowed = set(_CLI_MODE_COMMANDS["system"].get(style, [])) | \
        set(_CLI_MODE_COMMANDS["interface"].get(style, [])) | {"system-view", "end"}
    other_words = set(_CLI_MODE_COMMANDS["user"].get(other, [])) | \
        set(_CLI_MODE_COMMANDS["system"].get(other, [])) | \
        set(_CLI_MODE_COMMANDS["interface"].get(other, []))
    other_label = "思科/锐捷系" if style == "huawei_like" else "华为/H3C 系"

    results = []
    for raw in commands or []:
        cmd = (raw or "").strip()
        if not cmd or cmd.startswith(("!", "#")) or "WARNING" in cmd:
            continue
        first = cmd.split()[0].lower()
        if first in allowed:
            results.append({"command": raw, "level": "ok", "message": ""})
        elif first in other_words:
            results.append({"command": raw, "level": "error",
                            "message": f"\"{first}\" 是{other_label}命令, 与所选厂商语法不符"})
        else:
            results.append({"command": raw, "level": "warn",
                            "message": "知识库未收录该命令首词, 请人工确认"})
    return results

# Vendor-specific syntax templates for common operations.
# Each vendor has ~40 template keys covering basic L2, advanced switching,
# routing, high-availability, and security features.
_VENDOR_SYNTAX = {
    # ========================================================================
    # EXISTING 11 VENDORS (basic keys preserved exactly as-is)
    # ========================================================================

    # --- Huawei (switch base) ---
    "Huawei": {
        # ---- preserved basic keys ----
        "enter_config": "system-view",
        "hostname": "sysname {hostname}",
        "domain_name": "dns domain {domain}",
        "create_vlan": "vlan batch {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "port link-type access",
        "access_vlan": "port default vlan {vlan}",
        "trunk_mode": "port link-type trunk",
        "trunk_allow": "port trunk allow-pass vlan {vlans}",
        "trunk_pvid": "port trunk pvid vlan {vlan}",
        "stp_enable": "stp enable",
        "stp_mode": "stp mode rstp",
        "stp_edge": "stp edged-port enable",
        "mgmt_intf": "interface Vlanif {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "save",
        "show": "display current-configuration",
        "lldp": "display lldp neighbor brief",
        # ---- advanced switch keys ----
        "dhcp_enable": "dhcp enable",
        "dhcp_pool": "ip pool {pool_name}",
        "dhcp_gateway": "gateway-list {gw}",
        "dhcp_dns": "dns-list {dns}",
        "dhcp_excluded": "dhcp server excluded-ip-address {start} {end}",
        "port_security": "port-security enable",
        "port_security_max": "port-security max-mac-num {max}",
        "ip_source_guard": "ip source check user-bind enable",
        "static_route": "ip route-static {dest} {mask} {next_hop}",
        "port_mirror": "observe-port 1 interface GigabitEthernet0/0/{dst}\ninterface {src}\n port-mirroring to observe-port 1 both",
        "acl_deny_subnet": "acl number {num}\n rule deny ip source {src} {wildcard} destination {dst} {w_dst}",
        "acl_permit_tcp": "acl number {num}\n rule permit tcp source {src} {wildcard} destination {dst} {w_dst} destination-port eq {port}",
        "acl_apply_in": "traffic-filter inbound acl {num}",
        "vrrp_create": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_ip": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_priority": "vrrp vrid {vrid} priority {pri}",
        "mstp_region": "stp region-configuration\n region-name {name}\n instance {inst} vlan {vlans}\n active region-configuration",
        "mstp_instance": "stp instance {inst} root primary",
        "ospf_enable": "ospf {pid} router-id {rid}",
        "ospf_network": "area {area}\n  network {net} {wildcard}",
        "ospf_area": "area {area}",
        "policy_route": "policy-based-route {name} permit node {node}\n if-match acl {num}\n apply next-hop {next_hop}",
        # ---- Eth-Trunk / Link Aggregation ----
        "eth_trunk_create": "interface Eth-Trunk{id}",
        "eth_trunk_member": "eth-trunk {id}",
        "lacp_enable": "mode lacp-static",
        "eth_trunk_load_bal": "load-balance {mode}",
        "eth_trunk_min_links": "least active-links {n}",
        # ---- Global services ----
        "ntp_server": "ntp-service server {ip}",
        "snmp_community": "snmp-agent community read {community}",
        "aaa_local_user": "local-user {user} password irreversible-cipher {pwd}\n local-user {user} privilege level 15\n local-user {user} service-type ssh telnet http",
    },

    # --- Huawei Router ---
    "Huawei_router": {
        # ---- preserved basic keys (same as switch) ----
        "enter_config": "system-view",
        "hostname": "sysname {hostname}",
        "create_vlan": "vlan batch {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "port link-type access",
        "access_vlan": "port default vlan {vlan}",
        "trunk_mode": "port link-type trunk",
        "trunk_allow": "port trunk allow-pass vlan {vlans}",
        "trunk_pvid": "port trunk pvid vlan {vlan}",
        "stp_enable": "stp enable",
        "stp_mode": "stp mode rstp",
        "stp_edge": "stp edged-port enable",
        "mgmt_intf": "interface Vlanif {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "save",
        "show": "display current-configuration",
        "lldp": "display lldp neighbor brief",
        # ---- advanced switch keys ----
        "dhcp_enable": "dhcp enable",
        "dhcp_pool": "ip pool {pool_name}",
        "dhcp_gateway": "gateway-list {gw}",
        "dhcp_dns": "dns-list {dns}",
        "dhcp_excluded": "dhcp server excluded-ip-address {start} {end}",
        "port_security": "port-security enable",
        "port_security_max": "port-security max-mac-num {max}",
        "ip_source_guard": "ip source check user-bind enable",
        "static_route": "ip route-static {dest} {mask} {next_hop}",
        "port_mirror": "observe-port 1 interface GigabitEthernet0/0/{dst}\ninterface {src}\n port-mirroring to observe-port 1 both",
        "acl_deny_subnet": "acl number {num}\n rule deny ip source {src} {wildcard} destination {dst} {w_dst}",
        "acl_permit_tcp": "acl number {num}\n rule permit tcp source {src} {wildcard} destination {dst} {w_dst} destination-port eq {port}",
        "acl_apply_in": "traffic-filter inbound acl {num}",
        "vrrp_create": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_ip": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_priority": "vrrp vrid {vrid} priority {pri}",
        "mstp_region": "stp region-configuration\n region-name {name}\n instance {inst} vlan {vlans}\n active region-configuration",
        "mstp_instance": "stp instance {inst} root primary",
        "ospf_enable": "ospf {pid} router-id {rid}",
        "ospf_network": "area {area}\n  network {net} {wildcard}",
        "ospf_area": "area {area}",
        "policy_route": "policy-based-route {name} permit node {node}\n if-match acl {num}\n apply next-hop {next_hop}",
        # ---- router-specific keys ----
        "wan_pppoe": "interface Dialer0\n link-protocol ppp\n ppp chap user {user}\n ppp chap password {pwd}\n ppp ipcp dns request\n dialer user {user}\n dialer bundle 1",
        "wan_static_ip": "ip address {ip} {mask}",
        "wan_dhcp": "ip address dhcp-alloc",
        "nat_outbound": "nat outbound {acl_num}",
        "nat_server": "nat server protocol tcp global {public_ip} {public_port} inside {private_ip} {private_port}",
        "acl_deny_ip": "acl number {num}\n rule deny ip source {src} {wildcard}",
        "multi_isp_route": "ip route-static {dest} {mask} {isp1_gw} preference 60\nip route-static {dest} {mask} {isp2_gw} preference 100",
        "eth_trunk_create": "interface Eth-Trunk{id}",
        "eth_trunk_member": "eth-trunk {id}",
        "lacp_enable": "mode lacp-static",
        "eth_trunk_load_bal": "load-balance {mode}",
        "eth_trunk_min_links": "least active-links {n}",
    },

    # --- Huawei Firewall ---
    "Huawei_fw": {
        # ---- preserved basic keys (same as switch) ----
        "enter_config": "system-view",
        "hostname": "sysname {hostname}",
        "create_vlan": "vlan batch {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "port link-type access",
        "access_vlan": "port default vlan {vlan}",
        "trunk_mode": "port link-type trunk",
        "trunk_allow": "port trunk allow-pass vlan {vlans}",
        "trunk_pvid": "port trunk pvid vlan {vlan}",
        "stp_enable": "stp enable",
        "stp_mode": "stp mode rstp",
        "stp_edge": "stp edged-port enable",
        "mgmt_intf": "interface Vlanif {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "save",
        "show": "display current-configuration",
        "lldp": "display lldp neighbor brief",
        # ---- advanced switch keys ----
        "dhcp_enable": "dhcp enable",
        "dhcp_pool": "ip pool {pool_name}",
        "dhcp_gateway": "gateway-list {gw}",
        "dhcp_dns": "dns-list {dns}",
        "dhcp_excluded": "dhcp server excluded-ip-address {start} {end}",
        "port_security": "port-security enable",
        "port_security_max": "port-security max-mac-num {max}",
        "ip_source_guard": "ip source check user-bind enable",
        "static_route": "ip route-static {dest} {mask} {next_hop}",
        "port_mirror": "observe-port 1 interface GigabitEthernet0/0/{dst}\ninterface {src}\n port-mirroring to observe-port 1 both",
        "acl_deny_subnet": "acl number {num}\n rule deny ip source {src} {wildcard} destination {dst} {w_dst}",
        "acl_permit_tcp": "acl number {num}\n rule permit tcp source {src} {wildcard} destination {dst} {w_dst} destination-port eq {port}",
        "acl_apply_in": "traffic-filter inbound acl {num}",
        "vrrp_create": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_ip": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_priority": "vrrp vrid {vrid} priority {pri}",
        "mstp_region": "stp region-configuration\n region-name {name}\n instance {inst} vlan {vlans}\n active region-configuration",
        "mstp_instance": "stp instance {inst} root primary",
        "ospf_enable": "ospf {pid} router-id {rid}",
        "ospf_network": "area {area}\n  network {net} {wildcard}",
        "ospf_area": "area {area}",
        "policy_route": "policy-based-route {name} permit node {node}\n if-match acl {num}\n apply next-hop {next_hop}",
        # ---- firewall-specific keys ----
        "zone_create": "firewall zone name {zone}\n set priority {pri}",
        "zone_add_intf": "firewall zone name {zone}\n add interface {ifname}",
        "interzone_policy": "policy interzone {src_zone} {dst_zone} direction {dir}\n policy {num}\n  action permit\n  policy source {src_addr}\n  policy destination {dst_addr}",
        "fw_nat_server": "nat server {name} protocol tcp global {public_ip} {public_port} inside {private_ip} {private_port}",
        "fw_nat_outbound": "nat-policy\n rule name {name}\n source-zone {zone}\n destination-zone {dst_zone}\n action source-nat easy-ip",
        "fw_pppoe": "interface Dialer0\n link-protocol ppp\n ppp chap user {user}\n ppp chap password {pwd}",
        "fw_static_ip": "ip address {ip} {mask}",
    },

    # --- Cisco (switch base) ---
    "Cisco": {
        # ---- preserved basic keys ----
        "enter_config": "configure terminal",
        "hostname": "hostname {hostname}",
        "domain_name": "ip domain-name {domain}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "switchport mode access",
        "access_vlan": "switchport access vlan {vlan}",
        "trunk_mode": "switchport mode trunk",
        "trunk_allow": "switchport trunk allowed vlan {vlans}",
        "trunk_pvid": "switchport trunk native vlan {vlan}",
        "stp_enable": "spanning-tree vlan {vlans}",
        "stp_mode": "spanning-tree mode rapid-pvst",
        "stp_edge": "spanning-tree portfast",
        "mgmt_intf": "interface Vlan{vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "copy running-config startup-config",
        "show": "show running-config",
        "lldp": "show lldp neighbors",
        # ---- advanced switch keys ----
        "dhcp_enable": "service dhcp",
        "dhcp_pool": "ip dhcp pool {pool_name}",
        "dhcp_gateway": "default-router {gw}",
        "dhcp_dns": "dns-server {dns}",
        "dhcp_excluded": "ip dhcp excluded-address {start} {end}",
        "port_security": "switchport port-security",
        "port_security_max": "switchport port-security maximum {max}",
        "ip_source_guard": "ip verify source",
        "static_route": "ip route {dest} {mask} {next_hop}",
        "port_mirror": "monitor session 1 source interface {src} both\nmonitor session 1 destination interface {dst}",
        "acl_deny_subnet": "access-list {num} deny ip {src} {wildcard} {dst} {w_dst}",
        "acl_permit_tcp": "access-list {num} permit tcp {src} {wildcard} {dst} {w_dst} eq {port}",
        "acl_apply_in": "ip access-group {num} in",
        "vrrp_create": "vrrp {vrid} ip {vip}",
        "vrrp_ip": "vrrp {vrid} ip {vip}",
        "vrrp_priority": "vrrp {vrid} priority {pri}",
        "mstp_region": "spanning-tree mst configuration\n name {name}\n instance {inst} vlan {vlans}",
        "mstp_instance": "spanning-tree mst {inst} root primary",
        "ospf_enable": "router ospf {pid}\n router-id {rid}",
        "ospf_network": "network {net} {wildcard} area {area}",
        "ospf_area": "area {area} stub",
        "policy_route": "route-map {name} permit {node}\n match ip address {num}\n set ip next-hop {next_hop}",
        # ---- Port-Channel / Link Aggregation ----
        "eth_trunk_create": "interface Port-channel{id}",
        "eth_trunk_member": "channel-group {id} mode active",
        "lacp_enable": "lacp rate fast",
        "eth_trunk_load_bal": "port-channel load-balance {mode}",
        "eth_trunk_min_links": "port-channel min-links {n}",
        "ntp_server": "ntp server {ip}",
        "snmp_community": "snmp-server community {community} RO",
        "aaa_local_user": "username {user} privilege 15 secret {pwd}",
    },

    # --- Cisco Router ---
    "Cisco_router": {
        # ---- preserved basic keys ----
        "enter_config": "configure terminal",
        "hostname": "hostname {hostname}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "switchport mode access",
        "access_vlan": "switchport access vlan {vlan}",
        "trunk_mode": "switchport mode trunk",
        "trunk_allow": "switchport trunk allowed vlan {vlans}",
        "trunk_pvid": "switchport trunk native vlan {vlan}",
        "stp_enable": "spanning-tree vlan {vlans}",
        "stp_mode": "spanning-tree mode rapid-pvst",
        "stp_edge": "spanning-tree portfast",
        "mgmt_intf": "interface Vlan{vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "copy running-config startup-config",
        "show": "show running-config",
        "lldp": "show lldp neighbors",
        # ---- advanced switch keys ----
        "dhcp_enable": "service dhcp",
        "dhcp_pool": "ip dhcp pool {pool_name}",
        "dhcp_gateway": "default-router {gw}",
        "dhcp_dns": "dns-server {dns}",
        "dhcp_excluded": "ip dhcp excluded-address {start} {end}",
        "port_security": "switchport port-security",
        "port_security_max": "switchport port-security maximum {max}",
        "ip_source_guard": "ip verify source",
        "static_route": "ip route {dest} {mask} {next_hop}",
        "port_mirror": "monitor session 1 source interface {src} both\nmonitor session 1 destination interface {dst}",
        "acl_deny_subnet": "access-list {num} deny ip {src} {wildcard} {dst} {w_dst}",
        "acl_permit_tcp": "access-list {num} permit tcp {src} {wildcard} {dst} {w_dst} eq {port}",
        "acl_apply_in": "ip access-group {num} in",
        "vrrp_create": "vrrp {vrid} ip {vip}",
        "vrrp_ip": "vrrp {vrid} ip {vip}",
        "vrrp_priority": "vrrp {vrid} priority {pri}",
        "mstp_region": "spanning-tree mst configuration\n name {name}\n instance {inst} vlan {vlans}",
        "mstp_instance": "spanning-tree mst {inst} root primary",
        "ospf_enable": "router ospf {pid}\n router-id {rid}",
        "ospf_network": "network {net} {wildcard} area {area}",
        "ospf_area": "area {area} stub",
        "policy_route": "route-map {name} permit {node}\n match ip address {num}\n set ip next-hop {next_hop}",
        # ---- router-specific keys ----
        "wan_pppoe": "interface Dialer0\n ip address negotiated\n encapsulation ppp\n ppp chap hostname {user}\n ppp chap password {pwd}\n dialer pool 1",
        "wan_static_ip": "ip address {ip} {mask}",
        "wan_dhcp": "ip address dhcp",
        "nat_outbound": "ip nat inside source list {acl_num} interface Dialer0 overload",
        "nat_server": "ip nat inside source static tcp {private_ip} {private_port} {public_ip} {public_port}",
        "acl_deny_ip": "access-list {num} deny ip {src} {wildcard} any",
        "multi_isp_route": "ip route {dest} {mask} {isp1_gw} 10\nip route {dest} {mask} {isp2_gw} 20",
        "eth_trunk_create": "interface Port-channel{id}",
        "eth_trunk_member": "channel-group {id} mode active",
        "lacp_enable": "lacp rate fast",
        "eth_trunk_load_bal": "port-channel load-balance {mode}",
        "eth_trunk_min_links": "port-channel min-links {n}",
    },

    # --- H3C (switch base) ---
    "H3C": {
        # ---- preserved basic keys ----
        "enter_config": "system-view",
        "hostname": "sysname {hostname}",
        "domain_name": "dns domain {domain}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "port link-type access",
        "access_vlan": "port access vlan {vlan}",
        "trunk_mode": "port link-type trunk",
        "trunk_allow": "port trunk permit vlan {vlans}",
        "trunk_pvid": "port trunk pvid vlan {vlan}",
        "stp_enable": "stp enable",
        "stp_mode": "stp mode rstp",
        "stp_edge": "stp edged-port enable",
        "mgmt_intf": "interface Vlan-interface {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "save force",
        "show": "display current-configuration",
        "lldp": "display lldp neighbor-information list",
        # ---- advanced switch keys ----
        "dhcp_enable": "dhcp enable",
        "dhcp_pool": "ip pool {pool_name}",
        "dhcp_gateway": "gateway-list {gw}",
        "dhcp_dns": "dns-list {dns}",
        "dhcp_excluded": "dhcp server forbidden-ip {start} {end}",
        "port_security": "port-security enable",
        "port_security_max": "port-security max-mac-num {max}",
        "ip_source_guard": "ip verify source ip-address",
        "static_route": "ip route-static {dest} {mask} {next_hop}",
        "port_mirror": "mirroring-group 1 local\nmirroring-group 1 mirroring-port {src} both\nmirroring-group 1 monitor-port {dst}",
        "acl_deny_subnet": "acl number {num}\n rule deny ip source {src} {wildcard} destination {dst} {w_dst}",
        "acl_apply_in": "packet-filter {num} inbound",
        "vrrp_create": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_ip": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_priority": "vrrp vrid {vrid} priority {pri}",
        "mstp_region": "stp region-configuration\n region-name {name}\n instance {inst} vlan {vlans}\n active region-configuration",
        "mstp_instance": "stp instance {inst} root primary",
        "ospf_enable": "ospf {pid} router-id {rid}",
        "ospf_network": "area {area}\n  network {net} {wildcard}",
        "ospf_area": "area {area}",
        "policy_route": "policy-based-route {name} permit node {node}\n if-match acl {num}\n apply next-hop {next_hop}",
        "eth_trunk_create": "interface Eth-Trunk{id}",
        "eth_trunk_member": "eth-trunk {id}",
        "lacp_enable": "mode lacp-static",
        "eth_trunk_load_bal": "load-balance {mode}",
        "eth_trunk_min_links": "least active-links {n}",
        "ntp_server": "ntp-service server {ip}",
        "snmp_community": "snmp-agent community read {community}",
        "aaa_local_user": "local-user {user} password simple {pwd}\n local-user {user} privilege level 15\n local-user {user} service-type ssh telnet http",
    },

    # --- H3C Router ---
    "H3C_router": {
        # ---- preserved basic keys ----
        "enter_config": "system-view",
        "hostname": "sysname {hostname}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "port link-type access",
        "access_vlan": "port access vlan {vlan}",
        "trunk_mode": "port link-type trunk",
        "trunk_allow": "port trunk permit vlan {vlans}",
        "trunk_pvid": "port trunk pvid vlan {vlan}",
        "stp_enable": "stp enable",
        "stp_mode": "stp mode rstp",
        "stp_edge": "stp edged-port enable",
        "mgmt_intf": "interface Vlan-interface {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "save force",
        "show": "display current-configuration",
        "lldp": "display lldp neighbor-information list",
        # ---- advanced switch keys ----
        "dhcp_enable": "dhcp enable",
        "dhcp_pool": "ip pool {pool_name}",
        "dhcp_gateway": "gateway-list {gw}",
        "dhcp_dns": "dns-list {dns}",
        "dhcp_excluded": "dhcp server forbidden-ip {start} {end}",
        "port_security": "port-security enable",
        "port_security_max": "port-security max-mac-num {max}",
        "ip_source_guard": "ip verify source ip-address",
        "static_route": "ip route-static {dest} {mask} {next_hop}",
        "port_mirror": "mirroring-group 1 local\nmirroring-group 1 mirroring-port {src} both\nmirroring-group 1 monitor-port {dst}",
        "acl_deny_subnet": "acl number {num}\n rule deny ip source {src} {wildcard} destination {dst} {w_dst}",
        "acl_apply_in": "packet-filter {num} inbound",
        "vrrp_create": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_ip": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_priority": "vrrp vrid {vrid} priority {pri}",
        "mstp_region": "stp region-configuration\n region-name {name}\n instance {inst} vlan {vlans}\n active region-configuration",
        "mstp_instance": "stp instance {inst} root primary",
        "ospf_enable": "ospf {pid} router-id {rid}",
        "ospf_network": "area {area}\n  network {net} {wildcard}",
        "ospf_area": "area {area}",
        "policy_route": "policy-based-route {name} permit node {node}\n if-match acl {num}\n apply next-hop {next_hop}",
        # ---- router-specific keys ----
        "wan_pppoe": "interface Dialer0\n link-protocol ppp\n ppp chap user {user}\n ppp chap password {pwd}\n ppp ipcp dns request\n dialer user {user}\n dialer bundle 1",
        "wan_static_ip": "ip address {ip} {mask}",
        "wan_dhcp": "ip address dhcp-alloc",
        "nat_outbound": "nat outbound {acl_num}",
        "nat_server": "nat server protocol tcp global {public_ip} {public_port} inside {private_ip} {private_port}",
        "acl_deny_ip": "acl number {num}\n rule deny ip source {src} {wildcard}",
        "multi_isp_route": "ip route-static {dest} {mask} {isp1_gw} preference 60\nip route-static {dest} {mask} {isp2_gw} preference 100",
    },

    # --- H3C Firewall ---
    "H3C_fw": {
        # ---- preserved basic keys ----
        "enter_config": "system-view",
        "hostname": "sysname {hostname}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "port link-type access",
        "access_vlan": "port access vlan {vlan}",
        "trunk_mode": "port link-type trunk",
        "trunk_allow": "port trunk permit vlan {vlans}",
        "trunk_pvid": "port trunk pvid vlan {vlan}",
        "stp_enable": "stp enable",
        "stp_mode": "stp mode rstp",
        "stp_edge": "stp edged-port enable",
        "mgmt_intf": "interface Vlan-interface {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "save force",
        "show": "display current-configuration",
        "lldp": "display lldp neighbor-information list",
        # ---- advanced switch keys ----
        "dhcp_enable": "dhcp enable",
        "dhcp_pool": "ip pool {pool_name}",
        "dhcp_gateway": "gateway-list {gw}",
        "dhcp_dns": "dns-list {dns}",
        "dhcp_excluded": "dhcp server forbidden-ip {start} {end}",
        "port_security": "port-security enable",
        "port_security_max": "port-security max-mac-num {max}",
        "ip_source_guard": "ip verify source ip-address",
        "static_route": "ip route-static {dest} {mask} {next_hop}",
        "port_mirror": "mirroring-group 1 local\nmirroring-group 1 mirroring-port {src} both\nmirroring-group 1 monitor-port {dst}",
        "acl_deny_subnet": "acl number {num}\n rule deny ip source {src} {wildcard} destination {dst} {w_dst}",
        "acl_apply_in": "packet-filter {num} inbound",
        "vrrp_create": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_ip": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_priority": "vrrp vrid {vrid} priority {pri}",
        "mstp_region": "stp region-configuration\n region-name {name}\n instance {inst} vlan {vlans}\n active region-configuration",
        "mstp_instance": "stp instance {inst} root primary",
        "ospf_enable": "ospf {pid} router-id {rid}",
        "ospf_network": "area {area}\n  network {net} {wildcard}",
        "ospf_area": "area {area}",
        "policy_route": "policy-based-route {name} permit node {node}\n if-match acl {num}\n apply next-hop {next_hop}",
        # ---- firewall-specific keys ----
        "zone_create": "security-zone name {zone}\n priority {pri}",
        "zone_add_intf": "security-zone name {zone}\n import interface {ifname}",
        "interzone_policy": "zone-pair security source {src_zone} destination {dst_zone}\n object-policy apply ip {name}",
        "fw_nat_server": "nat server protocol tcp global {public_ip} {public_port} inside {private_ip} {private_port}",
        "fw_nat_outbound": "nat-policy\n rule name {name}\n source-zone {zone}\n destination-zone {dst_zone}\n action source-nat easy-ip",
        "fw_pppoe": "interface Dialer0\n link-protocol ppp\n ppp chap user {user}\n ppp chap password {pwd}",
        "fw_static_ip": "ip address {ip} {mask}",
    },

    # --- Juniper (switch) ---
    "Juniper": {
        # ---- preserved basic keys ----
        "enter_config": "configure",
        "hostname": "set system host-name {hostname}",
        "domain_name": "set system domain-name {domain}",
        "create_vlan": "set vlans VLAN{vlan} vlan-id {vlan}",
        "interface": "set interfaces {ifname} unit 0 family ethernet-switching",
        "access_mode": "set interfaces {ifname} unit 0 family ethernet-switching interface-mode access",
        "access_vlan": "set interfaces {ifname} unit 0 family ethernet-switching vlan members VLAN{vlan}",
        "trunk_mode": "set interfaces {ifname} unit 0 family ethernet-switching interface-mode trunk",
        "trunk_allow": "set interfaces {ifname} unit 0 family ethernet-switching vlan members [ {vlans_list} ]",
        "trunk_pvid": "set interfaces {ifname} native-vlan-id {vlan}",
        "stp_enable": "set protocols rstp",
        "stp_mode": "set protocols rstp",
        "stp_edge": "set protocols rstp interface {ifname} edge",
        "mgmt_intf": "set interfaces irb unit {vlan} family inet",
        "mgmt_ip": "set interfaces irb unit {vlan} family inet address {ip}/{prefix}",
        "save": "commit",
        "show": "show configuration",
        "lldp": "show lldp neighbors",
        # ---- advanced switch keys ----
        "dhcp_enable": "set system services dhcp-local-server group dhcp-group interface irb.{vlan}",
        "dhcp_pool": "set access address-assignment pool {pool_name} family inet network {net}/{prefix}",
        "dhcp_gateway": "set access address-assignment pool {pool_name} family inet dhcp-attributes router {gw}",
        "dhcp_dns": "set access address-assignment pool {pool_name} family inet dhcp-attributes name-server {dns}",
        "dhcp_excluded": "set access address-assignment pool {pool_name} family inet excluded-range {start} {end}",
        "port_security": "set ethernet-switching-options secure-access-port interface {ifname}",
        "port_security_max": "set ethernet-switching-options secure-access-port interface {ifname} mac-limit {max}",
        "ip_source_guard": "set ethernet-switching-options secure-access-port interface {ifname} ip-source-guard",
        "static_route": "set routing-options static route {dest}/{prefix} next-hop {next_hop}",
        "port_mirror": "set forwarding-options analyzer mirror input ingress interface {src}\nset forwarding-options analyzer mirror output interface {dst}",
        "acl_deny_subnet": "set firewall family inet filter {name} term 1 from source-address {src}/{prefix}\nset firewall family inet filter {name} term 1 from destination-address {dst}/{prefix}\nset firewall family inet filter {name} term 1 then discard",
        "acl_permit_tcp": "set firewall family inet filter {name} term 1 from source-address {src}/{prefix}\nset firewall family inet filter {name} term 1 from destination-address {dst}/{prefix}\nset firewall family inet filter {name} term 1 from protocol tcp\nset firewall family inet filter {name} term 1 from destination-port {port}\nset firewall family inet filter {name} term 1 then accept",
        "acl_apply_in": "set interfaces {ifname} unit 0 family inet filter input {name}",
        "vrrp_create": "set interfaces {ifname} unit 0 family inet address {ip}/{prefix} vrrp-group {vrid} virtual-address {vip}",
        "vrrp_ip": "set interfaces {ifname} unit 0 family inet address {ip}/{prefix} vrrp-group {vrid} virtual-address {vip}",
        "vrrp_priority": "set interfaces {ifname} unit 0 family inet address {ip}/{prefix} vrrp-group {vrid} priority {pri}",
        "mstp_region": "set protocols mstp configuration-name {name}\nset protocols mstp msti {inst} vlan [ {vlans_list} ]",
        "mstp_instance": "set protocols mstp msti {inst} bridge-priority 4096",
        "ospf_enable": "set protocols ospf area {area} interface {ifname}",
        "ospf_network": "set protocols ospf area {area} interface {ifname}",
        "ospf_area": "set protocols ospf area {area} stub",
        "policy_route": "set routing-options forwarding-table export {name}",
        "ntp_server": "set system ntp server {ip}",
        "snmp_community": "set snmp community {community} authorization read-only",
        "aaa_local_user": "set system login user {user} class superuser authentication plain-text-password {pwd}",
    },

    # --- Arista (switch) ---
    "Arista": {
        # ---- preserved basic keys ----
        "enter_config": "configure",
        "hostname": "hostname {hostname}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "switchport mode access",
        "access_vlan": "switchport access vlan {vlan}",
        "trunk_mode": "switchport mode trunk",
        "trunk_allow": "switchport trunk allowed vlan {vlans}",
        "trunk_pvid": "switchport trunk native vlan {vlan}",
        "stp_enable": "spanning-tree mode mstp",
        "stp_mode": "spanning-tree mode mstp",
        "stp_edge": "spanning-tree portfast",
        "mgmt_intf": "interface Vlan{vlan}",
        "mgmt_ip": "ip address {ip}/{prefix}",
        "save": "copy running-config startup-config",
        "show": "show running-config",
        "lldp": "show lldp neighbors",
        # ---- advanced switch keys ----
        "dhcp_enable": "service dhcp",
        "dhcp_pool": "ip dhcp pool {pool_name}",
        "dhcp_gateway": "default-router {gw}",
        "dhcp_dns": "dns-server {dns}",
        "dhcp_excluded": "ip dhcp excluded-address {start} {end}",
        "port_security": "switchport port-security",
        "port_security_max": "switchport port-security maximum {max}",
        "ip_source_guard": "ip verify source",
        "static_route": "ip route {dest}/{prefix} {next_hop}",
        "port_mirror": "monitor session 1 source interface {src} both\nmonitor session 1 destination interface {dst}",
        "acl_deny_subnet": "access-list {num} deny ip {src}/{prefix} {dst}/{prefix}",
        "acl_apply_in": "ip access-group {num} in",
        "vrrp_create": "vrrp {vrid} ip {vip}",
        "vrrp_ip": "vrrp {vrid} ip {vip}",
        "vrrp_priority": "vrrp {vrid} priority {pri}",
        "mstp_region": "spanning-tree mst configuration\n name {name}\n instance {inst} vlan {vlans}",
        "mstp_instance": "spanning-tree mst {inst} root primary",
        "ospf_enable": "router ospf {pid}\n router-id {rid}",
        "ospf_network": "network {net}/{prefix} area {area}",
        "ospf_area": "area {area} stub",
        "policy_route": "route-map {name} permit {node}\n match ip address {num}\n set ip next-hop {next_hop}",
    },

    # --- HPE / ArubaOS (switch) ---
    "HPE": {
        # ---- preserved basic keys ----
        "enter_config": "configure",
        "hostname": "hostname {hostname}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "vlan access {vlan}",
        "access_vlan": "",  # HPE access mode already sets VLAN
        "trunk_mode": "vlan trunk native {vlan}",
        "trunk_allow": "vlan trunk allowed {vlans}",
        "trunk_pvid": "vlan trunk native {vlan}",
        "stp_enable": "spanning-tree",
        "stp_mode": "spanning-tree mode rstp",
        "stp_edge": "spanning-tree port-type admin-edge",
        "mgmt_intf": "interface vlan {vlan}",
        "mgmt_ip": "ip address {ip}/{prefix}",
        "save": "write memory",
        "show": "show running-config",
        "lldp": "show lldp neighbor-info",
        # ---- advanced switch keys ----
        "dhcp_enable": "dhcp-server enable",
        "dhcp_pool": "dhcp-server pool {pool_name}",
        "dhcp_gateway": "default-router {gw}",
        "dhcp_dns": "dns-server {dns}",
        "dhcp_excluded": "dhcp-server excluded-address {start} {end}",
        "port_security": "port-access security",
        "port_security_max": "port-access security address-limit {max}",
        "ip_source_guard": "ip source-lockdown",
        "static_route": "ip route {dest} {mask} {next_hop}",
        "port_mirror": "mirror 1 port {src}\nmirror 1 monitor {dst}",
        "acl_deny_subnet": "access-list ip {name}\n deny ip {src} {wildcard} {dst} {w_dst}",
        "acl_apply_in": "apply access-list ip {name} in",
        "vrrp_create": "router vrrp ipv4 vrid {vrid} virtual-ip {vip}",
        "vrrp_ip": "router vrrp ipv4 vrid {vrid} virtual-ip {vip}",
        "vrrp_priority": "router vrrp ipv4 vrid {vrid} priority {pri}",
        "mstp_region": "spanning-tree mst configuration\n name {name}\n instance {inst} vlan {vlans}",
        "mstp_instance": "spanning-tree mst {inst} priority 4096",
        "ospf_enable": "router ospf\n router-id {rid}",
        "ospf_network": "area {area}\n network {net} {wildcard}",
        "ospf_area": "area {area} stub",
        "policy_route": "route-map {name} permit {node}\n match ip address {num}\n set ip next-hop {next_hop}",
    },

    # --- Ruijie (switch base) ---
    "Ruijie": {
        # ---- preserved basic keys ----
        "enter_config": "configure terminal",
        "hostname": "hostname {hostname}",
        "domain_name": "ip domain-name {domain}",
        "create_vlan": "vlan range {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "switchport mode access",
        "access_vlan": "switchport access vlan {vlan}",
        "trunk_mode": "switchport mode trunk",
        "trunk_allow": "switchport trunk allowed vlan {vlans}",
        "trunk_pvid": "switchport trunk native vlan {vlan}",
        "stp_enable": "spanning-tree",
        "stp_mode": "spanning-tree mode rstp",
        "stp_edge": "spanning-tree portfast",
        "mgmt_intf": "interface vlan {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "write memory",
        "show": "show running-config",
        "lldp": "show lldp neighbors",
        # ---- advanced switch keys ----
        "dhcp_enable": "service dhcp",
        "dhcp_pool": "ip dhcp pool {pool_name}",
        "dhcp_gateway": "default-router {gw}",
        "dhcp_dns": "dns-server {dns}",
        "dhcp_excluded": "ip dhcp excluded-address {start} {end}",
        "port_security": "switchport port-security",
        "port_security_max": "switchport port-security maximum {max}",
        "ip_source_guard": "ip verify source",
        "static_route": "ip route {dest} {mask} {next_hop}",
        "port_mirror": "monitor session 1 source interface {src} both\nmonitor session 1 destination interface {dst}",
        "acl_deny_subnet": "access-list {num} deny ip {src} {wildcard} {dst} {w_dst}",
        "acl_permit_tcp": "access-list {num} permit tcp {src} {wildcard} {dst} {w_dst} eq {port}",
        "acl_apply_in": "ip access-group {num} in",
        "vrrp_create": "vrrp {vrid} ip {vip}",
        "vrrp_ip": "vrrp {vrid} ip {vip}",
        "vrrp_priority": "vrrp {vrid} priority {pri}",
        "mstp_region": "spanning-tree mst configuration\n name {name}\n instance {inst} vlan {vlans}",
        "mstp_instance": "spanning-tree mst {inst} root primary",
        "ospf_enable": "router ospf {pid}\n router-id {rid}",
        "ospf_network": "network {net} {wildcard} area {area}",
        "ospf_area": "area {area} stub",
        "policy_route": "route-map {name} permit {node}\n match ip address {num}\n set ip next-hop {next_hop}",
        "eth_trunk_create": "interface Port-channel{id}",
        "eth_trunk_member": "channel-group {id} mode active",
        "lacp_enable": "lacp rate fast",
        "eth_trunk_load_bal": "port-channel load-balance {mode}",
        "eth_trunk_min_links": "port-channel min-links {n}",
        "ntp_server": "ntp server {ip}",
        "snmp_community": "snmp-server community {community} RO",
        "aaa_local_user": "username {user} privilege 15 password {pwd}",
    },

    # --- Ruijie Router ---
    "Ruijie_router": {
        # ---- preserved basic keys ----
        "enter_config": "configure terminal",
        "hostname": "hostname {hostname}",
        "create_vlan": "vlan range {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "switchport mode access",
        "access_vlan": "switchport access vlan {vlan}",
        "trunk_mode": "switchport mode trunk",
        "trunk_allow": "switchport trunk allowed vlan {vlans}",
        "trunk_pvid": "switchport trunk native vlan {vlan}",
        "stp_enable": "spanning-tree",
        "stp_mode": "spanning-tree mode rstp",
        "stp_edge": "spanning-tree portfast",
        "mgmt_intf": "interface vlan {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "write memory",
        "show": "show running-config",
        "lldp": "show lldp neighbors",
        # ---- advanced switch keys ----
        "dhcp_enable": "service dhcp",
        "dhcp_pool": "ip dhcp pool {pool_name}",
        "dhcp_gateway": "default-router {gw}",
        "dhcp_dns": "dns-server {dns}",
        "dhcp_excluded": "ip dhcp excluded-address {start} {end}",
        "port_security": "switchport port-security",
        "port_security_max": "switchport port-security maximum {max}",
        "ip_source_guard": "ip verify source",
        "static_route": "ip route {dest} {mask} {next_hop}",
        "port_mirror": "monitor session 1 source interface {src} both\nmonitor session 1 destination interface {dst}",
        "acl_deny_subnet": "access-list {num} deny ip {src} {wildcard} {dst} {w_dst}",
        "acl_permit_tcp": "access-list {num} permit tcp {src} {wildcard} {dst} {w_dst} eq {port}",
        "acl_apply_in": "ip access-group {num} in",
        "vrrp_create": "vrrp {vrid} ip {vip}",
        "vrrp_ip": "vrrp {vrid} ip {vip}",
        "vrrp_priority": "vrrp {vrid} priority {pri}",
        "mstp_region": "spanning-tree mst configuration\n name {name}\n instance {inst} vlan {vlans}",
        "mstp_instance": "spanning-tree mst {inst} root primary",
        "ospf_enable": "router ospf {pid}\n router-id {rid}",
        "ospf_network": "network {net} {wildcard} area {area}",
        "ospf_area": "area {area} stub",
        "policy_route": "route-map {name} permit {node}\n match ip address {num}\n set ip next-hop {next_hop}",
        # ---- router-specific keys ----
        "wan_pppoe": "interface Dialer0\n ip address negotiated\n encapsulation ppp\n ppp chap hostname {user}\n ppp chap password {pwd}\n dialer pool 1",
        "wan_static_ip": "ip address {ip} {mask}",
        "wan_dhcp": "ip address dhcp",
        "nat_outbound": "ip nat inside source list {acl_num} interface Dialer0 overload",
        "nat_server": "ip nat inside source static tcp {private_ip} {private_port} {public_ip} {public_port}",
        "acl_deny_ip": "access-list {num} deny ip {src} {wildcard} any",
        "multi_isp_route": "ip route {dest} {mask} {isp1_gw} 10\nip route {dest} {mask} {isp2_gw} 20",
    },

    # --- Zte (switch) ---
    "Zte": {
        # ---- preserved basic keys ----
        "enter_config": "configure terminal",
        "hostname": "hostname {hostname}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "switchport mode access",
        "access_vlan": "switchport access vlan {vlan}",
        "trunk_mode": "switchport mode trunk",
        "trunk_allow": "switchport trunk vlan {vlans}",
        "trunk_pvid": "switchport trunk native vlan {vlan}",
        "stp_enable": "spanning-tree enable",
        "stp_mode": "spanning-tree mode rstp",
        "stp_edge": "spanning-tree edge-port",
        "mgmt_intf": "interface vlan {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "write",
        "show": "show running-config",
        "lldp": "show lldp neighbors",
        # ---- advanced switch keys ----
        "dhcp_enable": "service dhcp",
        "dhcp_pool": "ip dhcp pool {pool_name}",
        "dhcp_gateway": "default-router {gw}",
        "dhcp_dns": "dns-server {dns}",
        "dhcp_excluded": "ip dhcp excluded-address {start} {end}",
        "port_security": "switchport port-security",
        "port_security_max": "switchport port-security maximum {max}",
        "ip_source_guard": "ip verify source",
        "static_route": "ip route {dest} {mask} {next_hop}",
        "port_mirror": "monitor session 1 source interface {src} both\nmonitor session 1 destination interface {dst}",
        "acl_deny_subnet": "access-list {num} deny ip {src} {wildcard} {dst} {w_dst}",
        "acl_permit_tcp": "access-list {num} permit tcp {src} {wildcard} {dst} {w_dst} eq {port}",
        "acl_apply_in": "ip access-group {num} in",
        "vrrp_create": "vrrp {vrid} ip {vip}",
        "vrrp_ip": "vrrp {vrid} ip {vip}",
        "vrrp_priority": "vrrp {vrid} priority {pri}",
        "mstp_region": "spanning-tree mst configuration\n name {name}\n instance {inst} vlan {vlans}",
        "mstp_instance": "spanning-tree mst {inst} root primary",
        "ospf_enable": "router ospf {pid}\n router-id {rid}",
        "ospf_network": "network {net} {wildcard} area {area}",
        "ospf_area": "area {area} stub",
        "policy_route": "route-map {name} permit {node}\n match ip address {num}\n set ip next-hop {next_hop}",
    },

    # --- Extreme (switch) ---
    "Extreme": {
        # ---- preserved basic keys ----
        "enter_config": "",  # Extreme commands work from enable mode
        "hostname": "configure sysname {hostname}",
        "create_vlan": "create vlan {vlan_name}\nconfigure vlan {vlan_name} tag {vlan}",
        "interface": "",
        "access_mode": "configure vlan {vlan_name} add ports {ifname} untagged",
        "access_vlan": "",  # Already set via access_mode
        "trunk_mode": "configure vlan {vlan_name} add ports {ifname} tagged",
        "trunk_allow": "",
        "trunk_pvid": "configure vlan {vlan_name} add ports {ifname} untagged",
        "stp_enable": "enable stp",
        "stp_mode": "",
        "stp_edge": "configure stp ports {ifname} edge-port true",
        "mgmt_intf": "configure vlan {vlan_name} ipaddress {ip}/{prefix}",
        "mgmt_ip": "",
        "save": "save configuration primary",
        "show": "show configuration",
        "lldp": "show lldp neighbors",
        # ---- advanced switch keys ----
        "dhcp_enable": "enable dhcp",
        "dhcp_pool": "configure vlan {pool_name} dhcp-address-range {start} - {end}",
        "dhcp_gateway": "configure vlan {pool_name} dhcp-options default-gateway {gw}",
        "dhcp_dns": "configure vlan {pool_name} dhcp-options dns-server {dns}",
        "dhcp_excluded": "configure vlan {pool_name} dhcp-address-range {start} - {end}",
        "port_security": "configure ports {ifname} port-security enable",
        "port_security_max": "configure ports {ifname} port-security max-mac {max}",
        "ip_source_guard": "configure ports {ifname} ip-source-guard enable",
        "static_route": "configure iproute add {dest}/{prefix} {next_hop}",
        "port_mirror": "enable mirroring to port {dst}\nconfigure mirroring add port {src}",
        "acl_deny_subnet": "create access-list {name}\nconfigure access-list {name} deny ip {src}/{prefix} {dst}/{prefix}",
        "acl_apply_in": "configure access-list {name} ports {ifname} ingress",
        "vrrp_create": "configure vrrp vlan {vlan_name} vrid {vrid} virtual-ip {vip}",
        "vrrp_ip": "configure vrrp vlan {vlan_name} vrid {vrid} virtual-ip {vip}",
        "vrrp_priority": "configure vrrp vlan {vlan_name} vrid {vrid} priority {pri}",
        "mstp_region": "configure mstp region {name}\nconfigure mstp instance {inst} vlan {vlans}",
        "mstp_instance": "configure mstp instance {inst} priority 4096",
        "ospf_enable": "enable ospf",
        "ospf_network": "configure ospf add vlan {vlan_name} area {area}",
        "ospf_area": "configure ospf area {area} stub",
        "policy_route": "configure policy route-map {name} permit {node}\nconfigure policy route-map {name} match ip address {num}\nconfigure policy route-map {name} set next-hop {next_hop}",
    },

    # --- Dell (switch) ---
    "Dell": {
        # ---- preserved basic keys ----
        "enter_config": "configure terminal",
        "hostname": "hostname {hostname}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "switchport mode access",
        "access_vlan": "switchport access vlan {vlan}",
        "trunk_mode": "switchport mode trunk",
        "trunk_allow": "switchport trunk allowed vlan {vlans}",
        "trunk_pvid": "switchport trunk native vlan {vlan}",
        "stp_enable": "spanning-tree",
        "stp_mode": "spanning-tree mode rstp",
        "stp_edge": "spanning-tree portfast",
        "mgmt_intf": "interface vlan {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "copy running-config startup-config",
        "show": "show running-config",
        "lldp": "show lldp neighbors",
        # ---- advanced switch keys ----
        "dhcp_enable": "service dhcp",
        "dhcp_pool": "ip dhcp pool {pool_name}",
        "dhcp_gateway": "default-router {gw}",
        "dhcp_dns": "dns-server {dns}",
        "dhcp_excluded": "ip dhcp excluded-address {start} {end}",
        "port_security": "switchport port-security",
        "port_security_max": "switchport port-security maximum {max}",
        "ip_source_guard": "ip verify source",
        "static_route": "ip route {dest} {mask} {next_hop}",
        "port_mirror": "monitor session 1 source interface {src} both\nmonitor session 1 destination interface {dst}",
        "acl_deny_subnet": "access-list {num} deny ip {src} {wildcard} {dst} {w_dst}",
        "acl_permit_tcp": "access-list {num} permit tcp {src} {wildcard} {dst} {w_dst} eq {port}",
        "acl_apply_in": "ip access-group {num} in",
        "vrrp_create": "vrrp {vrid} ip {vip}",
        "vrrp_ip": "vrrp {vrid} ip {vip}",
        "vrrp_priority": "vrrp {vrid} priority {pri}",
        "mstp_region": "spanning-tree mst configuration\n name {name}\n instance {inst} vlan {vlans}",
        "mstp_instance": "spanning-tree mst {inst} root primary",
        "ospf_enable": "router ospf {pid}\n router-id {rid}",
        "ospf_network": "network {net} {wildcard} area {area}",
        "ospf_area": "area {area} stub",
        "policy_route": "route-map {name} permit {node}\n match ip address {num}\n set ip next-hop {next_hop}",
    },

    # --- Sonic / SONiC (switch) ---
    "Sonic": {
        # ---- preserved basic keys ----
        "enter_config": "",
        "hostname": "sudo config hostname {hostname}",
        "create_vlan": "sudo config vlan add {vlan}",
        "interface": "",
        "access_mode": "sudo config vlan member add {vlan} {ifname}",
        "access_vlan": "",
        "trunk_mode": "sudo config interface vlan add {ifname} {vlan}",
        "trunk_allow": "",
        "trunk_pvid": "",
        "stp_enable": "sudo systemctl start stpd",
        "stp_mode": "",
        "stp_edge": "",
        "mgmt_intf": "sudo config interface ip add Vlan{vlan}",
        "mgmt_ip": "sudo config interface ip add Vlan{vlan} {ip}/{prefix}",
        "save": "sudo config save -y",
        "show": "show runningconfiguration all",
        "lldp": "show lldp table",
        # ---- advanced switch keys ----
        "dhcp_enable": "sudo config dhcp_relay add {vlan} {server_ip}",
        "dhcp_pool": "sudo config vlan dhcp_relay add {pool_name} {server_ip}",
        "dhcp_gateway": "sudo config interface ip add Vlan{vlan} {gw}/{prefix}",
        "dhcp_dns": "",
        "dhcp_excluded": "",
        "port_security": "sudo config port-security {ifname} enable",
        "port_security_max": "sudo config port-security {ifname} max-mac {max}",
        "ip_source_guard": "",
        "static_route": "sudo config route add prefix {dest}/{prefix} nexthop {next_hop}",
        "port_mirror": "sudo config mirror_session add sess1 src {src} dst {dst}",
        "acl_deny_subnet": "sudo config acl rule add {name} deny ip {src}/{prefix} {dst}/{prefix}",
        "acl_apply_in": "sudo config acl add {name} {ifname} in",
        "vrrp_create": "sudo config vrrp create {vrid} {vip}",
        "vrrp_ip": "sudo config vrrp create {vrid} {vip}",
        "vrrp_priority": "sudo config vrrp set {vrid} priority {pri}",
        "mstp_region": "sudo config mstp region {name}\nsudo config mstp instance {inst} vlan {vlans}",
        "mstp_instance": "sudo config mstp instance {inst} priority 4096",
        "ospf_enable": "sudo config ospf router-id {rid}",
        "ospf_network": "sudo config ospf area {area} network {net}/{prefix}",
        "ospf_area": "sudo config ospf area {area} stub",
        "policy_route": "",
    },

    # ========================================================================
    # NEW 9 SWITCH VENDORS
    # ========================================================================

    # --- Maipu (迈普) - CLI similar to Huawei ---
    "Maipu": {
        "enter_config": "system-view",
        "hostname": "sysname {hostname}",
        "create_vlan": "vlan batch {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "port link-type access",
        "access_vlan": "port default vlan {vlan}",
        "trunk_mode": "port link-type trunk",
        "trunk_allow": "port trunk allow-pass vlan {vlans}",
        "trunk_pvid": "port trunk pvid vlan {vlan}",
        "stp_enable": "stp enable",
        "stp_mode": "stp mode rstp",
        "stp_edge": "stp edged-port enable",
        "mgmt_intf": "interface Vlanif {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "save",
        "show": "display current-configuration",
        "lldp": "display lldp neighbor brief",
        # advanced switch
        "dhcp_enable": "dhcp enable",
        "dhcp_pool": "ip pool {pool_name}",
        "dhcp_gateway": "gateway-list {gw}",
        "dhcp_dns": "dns-list {dns}",
        "dhcp_excluded": "dhcp server excluded-ip-address {start} {end}",
        "port_security": "port-security enable",
        "port_security_max": "port-security max-mac-num {max}",
        "ip_source_guard": "ip source check user-bind enable",
        "static_route": "ip route-static {dest} {mask} {next_hop}",
        "port_mirror": "monitor-port {dst}\ninterface {src}\n mirror-to monitor-port both",
        "acl_deny_subnet": "acl number {num}\n rule deny ip source {src} {wildcard} destination {dst} {w_dst}",
        "acl_permit_tcp": "acl number {num}\n rule permit tcp source {src} {wildcard} destination {dst} {w_dst} destination-port eq {port}",
        "acl_apply_in": "traffic-filter inbound acl {num}",
        "vrrp_create": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_ip": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_priority": "vrrp vrid {vrid} priority {pri}",
        "mstp_region": "stp region-configuration\n region-name {name}\n instance {inst} vlan {vlans}\n active region-configuration",
        "mstp_instance": "stp instance {inst} root primary",
        "ospf_enable": "ospf {pid} router-id {rid}",
        "ospf_network": "area {area}\n  network {net} {wildcard}",
        "ospf_area": "area {area}",
        "policy_route": "policy-based-route {name} permit node {node}\n if-match acl {num}\n apply next-hop {next_hop}",
    },

    # --- Hikvision (海康) - CLI similar to Cisco ---
    "Hikvision": {
        "enter_config": "configure terminal",
        "hostname": "hostname {hostname}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "switchport mode access",
        "access_vlan": "switchport access vlan {vlan}",
        "trunk_mode": "switchport mode trunk",
        "trunk_allow": "switchport trunk allowed vlan {vlans}",
        "trunk_pvid": "switchport trunk native vlan {vlan}",
        "stp_enable": "spanning-tree",
        "stp_mode": "spanning-tree mode rstp",
        "stp_edge": "spanning-tree portfast",
        "mgmt_intf": "interface vlan {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "copy running-config startup-config",
        "show": "show running-config",
        "lldp": "show lldp neighbors",
        # advanced switch
        "dhcp_enable": "service dhcp",
        "dhcp_pool": "ip dhcp pool {pool_name}",
        "dhcp_gateway": "default-router {gw}",
        "dhcp_dns": "dns-server {dns}",
        "dhcp_excluded": "ip dhcp excluded-address {start} {end}",
        "port_security": "switchport port-security",
        "port_security_max": "switchport port-security maximum {max}",
        "ip_source_guard": "ip verify source",
        "static_route": "ip route {dest} {mask} {next_hop}",
        "port_mirror": "monitor session 1 source interface {src} both\nmonitor session 1 destination interface {dst}",
        "acl_deny_subnet": "access-list {num} deny ip {src} {wildcard} {dst} {w_dst}",
        "acl_permit_tcp": "access-list {num} permit tcp {src} {wildcard} {dst} {w_dst} eq {port}",
        "acl_apply_in": "ip access-group {num} in",
        "vrrp_create": "vrrp {vrid} ip {vip}",
        "vrrp_ip": "vrrp {vrid} ip {vip}",
        "vrrp_priority": "vrrp {vrid} priority {pri}",
        "mstp_region": "spanning-tree mst configuration\n name {name}\n instance {inst} vlan {vlans}",
        "mstp_instance": "spanning-tree mst {inst} root primary",
        "ospf_enable": "router ospf {pid}\n router-id {rid}",
        "ospf_network": "network {net} {wildcard} area {area}",
        "ospf_area": "area {area} stub",
        "policy_route": "route-map {name} permit {node}\n match ip address {num}\n set ip next-hop {next_hop}",
    },

    # --- Tplink (TP-LINK) - CLI similar to Cisco ---
    "Tplink": {
        "enter_config": "configure terminal",
        "hostname": "hostname {hostname}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "switchport mode access",
        "access_vlan": "switchport access vlan {vlan}",
        "trunk_mode": "switchport mode trunk",
        "trunk_allow": "switchport trunk allowed vlan {vlans}",
        "trunk_pvid": "switchport trunk native vlan {vlan}",
        "stp_enable": "spanning-tree",
        "stp_mode": "spanning-tree mode rstp",
        "stp_edge": "spanning-tree portfast",
        "mgmt_intf": "interface vlan {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "copy running-config startup-config",
        "show": "show running-config",
        "lldp": "show lldp neighbors",
        # advanced switch
        "dhcp_enable": "service dhcp",
        "dhcp_pool": "ip dhcp pool {pool_name}",
        "dhcp_gateway": "default-router {gw}",
        "dhcp_dns": "dns-server {dns}",
        "dhcp_excluded": "ip dhcp excluded-address {start} {end}",
        "port_security": "switchport port-security",
        "port_security_max": "switchport port-security maximum {max}",
        "ip_source_guard": "ip verify source",
        "static_route": "ip route {dest} {mask} {next_hop}",
        "port_mirror": "monitor session 1 source interface {src} both\nmonitor session 1 destination interface {dst}",
        "acl_deny_subnet": "access-list {num} deny ip {src} {wildcard} {dst} {w_dst}",
        "acl_permit_tcp": "access-list {num} permit tcp {src} {wildcard} {dst} {w_dst} eq {port}",
        "acl_apply_in": "ip access-group {num} in",
        "vrrp_create": "vrrp {vrid} ip {vip}",
        "vrrp_ip": "vrrp {vrid} ip {vip}",
        "vrrp_priority": "vrrp {vrid} priority {pri}",
        "mstp_region": "spanning-tree mst configuration\n name {name}\n instance {inst} vlan {vlans}",
        "mstp_instance": "spanning-tree mst {inst} root primary",
        "ospf_enable": "router ospf {pid}\n router-id {rid}",
        "ospf_network": "network {net} {wildcard} area {area}",
        "ospf_area": "area {area} stub",
        "policy_route": "route-map {name} permit {node}\n match ip address {num}\n set ip next-hop {next_hop}",
    },

    # --- Fiberhome (烽火) - CLI similar to Huawei ---
    "Fiberhome": {
        "enter_config": "system-view",
        "hostname": "sysname {hostname}",
        "create_vlan": "vlan batch {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "port link-type access",
        "access_vlan": "port default vlan {vlan}",
        "trunk_mode": "port link-type trunk",
        "trunk_allow": "port trunk allow-pass vlan {vlans}",
        "trunk_pvid": "port trunk pvid vlan {vlan}",
        "stp_enable": "stp enable",
        "stp_mode": "stp mode rstp",
        "stp_edge": "stp edged-port enable",
        "mgmt_intf": "interface Vlanif {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "save",
        "show": "display current-configuration",
        "lldp": "display lldp neighbor brief",
        # advanced switch
        "dhcp_enable": "dhcp enable",
        "dhcp_pool": "ip pool {pool_name}",
        "dhcp_gateway": "gateway-list {gw}",
        "dhcp_dns": "dns-list {dns}",
        "dhcp_excluded": "dhcp server excluded-ip-address {start} {end}",
        "port_security": "port-security enable",
        "port_security_max": "port-security max-mac-num {max}",
        "ip_source_guard": "ip source check user-bind enable",
        "static_route": "ip route-static {dest} {mask} {next_hop}",
        "port_mirror": "mirror-port {src} both",
        "acl_deny_subnet": "acl number {num}\n rule deny ip source {src} {wildcard} destination {dst} {w_dst}",
        "acl_permit_tcp": "acl number {num}\n rule permit tcp source {src} {wildcard} destination {dst} {w_dst} destination-port eq {port}",
        "acl_apply_in": "traffic-filter inbound acl {num}",
        "vrrp_create": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_ip": "vrrp vrid {vrid} virtual-ip {vip}",
        "vrrp_priority": "vrrp vrid {vrid} priority {pri}",
        "mstp_region": "stp region-configuration\n region-name {name}\n instance {inst} vlan {vlans}\n active region-configuration",
        "mstp_instance": "stp instance {inst} root primary",
        "ospf_enable": "ospf {pid} router-id {rid}",
        "ospf_network": "area {area}\n  network {net} {wildcard}",
        "ospf_area": "area {area}",
        "policy_route": "policy-based-route {name} permit node {node}\n if-match acl {num}\n apply next-hop {next_hop}",
    },

    # --- Dptecn (迪普) - CLI similar to Cisco ---
    "Dptecn": {
        "enter_config": "configure terminal",
        "hostname": "hostname {hostname}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "switchport mode access",
        "access_vlan": "switchport access vlan {vlan}",
        "trunk_mode": "switchport mode trunk",
        "trunk_allow": "switchport trunk allowed vlan {vlans}",
        "trunk_pvid": "switchport trunk native vlan {vlan}",
        "stp_enable": "spanning-tree",
        "stp_mode": "spanning-tree mode rstp",
        "stp_edge": "spanning-tree portfast",
        "mgmt_intf": "interface vlan {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "write memory",
        "show": "show running-config",
        "lldp": "show lldp neighbors",
        # advanced switch
        "dhcp_enable": "service dhcp",
        "dhcp_pool": "ip dhcp pool {pool_name}",
        "dhcp_gateway": "default-router {gw}",
        "dhcp_dns": "dns-server {dns}",
        "dhcp_excluded": "ip dhcp excluded-address {start} {end}",
        "port_security": "switchport port-security",
        "port_security_max": "switchport port-security maximum {max}",
        "ip_source_guard": "ip verify source",
        "static_route": "ip route {dest} {mask} {next_hop}",
        "port_mirror": "monitor session 1 source interface {src} both\nmonitor session 1 destination interface {dst}",
        "acl_deny_subnet": "access-list {num} deny ip {src} {wildcard} {dst} {w_dst}",
        "acl_permit_tcp": "access-list {num} permit tcp {src} {wildcard} {dst} {w_dst} eq {port}",
        "acl_apply_in": "ip access-group {num} in",
        "vrrp_create": "vrrp {vrid} ip {vip}",
        "vrrp_ip": "vrrp {vrid} ip {vip}",
        "vrrp_priority": "vrrp {vrid} priority {pri}",
        "mstp_region": "spanning-tree mst configuration\n name {name}\n instance {inst} vlan {vlans}",
        "mstp_instance": "spanning-tree mst {inst} root primary",
        "ospf_enable": "router ospf {pid}\n router-id {rid}",
        "ospf_network": "network {net} {wildcard} area {area}",
        "ospf_area": "area {area} stub",
        "policy_route": "route-map {name} permit {node}\n match ip address {num}\n set ip next-hop {next_hop}",
    },

    # --- Inspur (浪潮) - CLI similar to Cisco ---
    "Inspur": {
        "enter_config": "configure terminal",
        "hostname": "hostname {hostname}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "switchport mode access",
        "access_vlan": "switchport access vlan {vlan}",
        "trunk_mode": "switchport mode trunk",
        "trunk_allow": "switchport trunk allowed vlan {vlans}",
        "trunk_pvid": "switchport trunk native vlan {vlan}",
        "stp_enable": "spanning-tree",
        "stp_mode": "spanning-tree mode rstp",
        "stp_edge": "spanning-tree portfast",
        "mgmt_intf": "interface vlan {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "copy running-config startup-config",
        "show": "show running-config",
        "lldp": "show lldp neighbors",
        # advanced switch
        "dhcp_enable": "service dhcp",
        "dhcp_pool": "ip dhcp pool {pool_name}",
        "dhcp_gateway": "default-router {gw}",
        "dhcp_dns": "dns-server {dns}",
        "dhcp_excluded": "ip dhcp excluded-address {start} {end}",
        "port_security": "switchport port-security",
        "port_security_max": "switchport port-security maximum {max}",
        "ip_source_guard": "ip verify source",
        "static_route": "ip route {dest} {mask} {next_hop}",
        "port_mirror": "monitor session 1 source interface {src} both\nmonitor session 1 destination interface {dst}",
        "acl_deny_subnet": "access-list {num} deny ip {src} {wildcard} {dst} {w_dst}",
        "acl_permit_tcp": "access-list {num} permit tcp {src} {wildcard} {dst} {w_dst} eq {port}",
        "acl_apply_in": "ip access-group {num} in",
        "vrrp_create": "vrrp {vrid} ip {vip}",
        "vrrp_ip": "vrrp {vrid} ip {vip}",
        "vrrp_priority": "vrrp {vrid} priority {pri}",
        "mstp_region": "spanning-tree mst configuration\n name {name}\n instance {inst} vlan {vlans}",
        "mstp_instance": "spanning-tree mst {inst} root primary",
        "ospf_enable": "router ospf {pid}\n router-id {rid}",
        "ospf_network": "network {net} {wildcard} area {area}",
        "ospf_area": "area {area} stub",
        "policy_route": "route-map {name} permit {node}\n match ip address {num}\n set ip next-hop {next_hop}",
    },

    # --- Boda (博达) - CLI similar to Cisco ---
    "Boda": {
        "enter_config": "configure terminal",
        "hostname": "hostname {hostname}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "switchport mode access",
        "access_vlan": "switchport access vlan {vlan}",
        "trunk_mode": "switchport mode trunk",
        "trunk_allow": "switchport trunk allowed vlan {vlans}",
        "trunk_pvid": "switchport trunk native vlan {vlan}",
        "stp_enable": "spanning-tree",
        "stp_mode": "spanning-tree mode rstp",
        "stp_edge": "spanning-tree portfast",
        "mgmt_intf": "interface vlan {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "copy running-config startup-config",
        "show": "show running-config",
        "lldp": "show lldp neighbors",
        # advanced switch
        "dhcp_enable": "service dhcp",
        "dhcp_pool": "ip dhcp pool {pool_name}",
        "dhcp_gateway": "default-router {gw}",
        "dhcp_dns": "dns-server {dns}",
        "dhcp_excluded": "ip dhcp excluded-address {start} {end}",
        "port_security": "switchport port-security",
        "port_security_max": "switchport port-security maximum {max}",
        "ip_source_guard": "ip verify source",
        "static_route": "ip route {dest} {mask} {next_hop}",
        "port_mirror": "monitor session 1 source interface {src} both\nmonitor session 1 destination interface {dst}",
        "acl_deny_subnet": "access-list {num} deny ip {src} {wildcard} {dst} {w_dst}",
        "acl_permit_tcp": "access-list {num} permit tcp {src} {wildcard} {dst} {w_dst} eq {port}",
        "acl_apply_in": "ip access-group {num} in",
        "vrrp_create": "vrrp {vrid} ip {vip}",
        "vrrp_ip": "vrrp {vrid} ip {vip}",
        "vrrp_priority": "vrrp {vrid} priority {pri}",
        "mstp_region": "spanning-tree mst configuration\n name {name}\n instance {inst} vlan {vlans}",
        "mstp_instance": "spanning-tree mst {inst} root primary",
        "ospf_enable": "router ospf {pid}\n router-id {rid}",
        "ospf_network": "network {net} {wildcard} area {area}",
        "ospf_area": "area {area} stub",
        "policy_route": "route-map {name} permit {node}\n match ip address {num}\n set ip next-hop {next_hop}",
    },

    # --- Raisecom (瑞斯康达) - CLI similar to Cisco ---
    "Raisecom": {
        "enter_config": "configure terminal",
        "hostname": "hostname {hostname}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "switchport mode access",
        "access_vlan": "switchport access vlan {vlan}",
        "trunk_mode": "switchport mode trunk",
        "trunk_allow": "switchport trunk allowed vlan {vlans}",
        "trunk_pvid": "switchport trunk native vlan {vlan}",
        "stp_enable": "spanning-tree",
        "stp_mode": "spanning-tree mode rstp",
        "stp_edge": "spanning-tree portfast",
        "mgmt_intf": "interface vlan {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "copy running-config startup-config",
        "show": "show running-config",
        "lldp": "show lldp neighbors",
        # advanced switch
        "dhcp_enable": "service dhcp",
        "dhcp_pool": "ip dhcp pool {pool_name}",
        "dhcp_gateway": "default-router {gw}",
        "dhcp_dns": "dns-server {dns}",
        "dhcp_excluded": "ip dhcp excluded-address {start} {end}",
        "port_security": "switchport port-security",
        "port_security_max": "switchport port-security maximum {max}",
        "ip_source_guard": "ip verify source",
        "static_route": "ip route {dest} {mask} {next_hop}",
        "port_mirror": "monitor session 1 source interface {src} both\nmonitor session 1 destination interface {dst}",
        "acl_deny_subnet": "access-list {num} deny ip {src} {wildcard} {dst} {w_dst}",
        "acl_permit_tcp": "access-list {num} permit tcp {src} {wildcard} {dst} {w_dst} eq {port}",
        "acl_apply_in": "ip access-group {num} in",
        "vrrp_create": "vrrp {vrid} ip {vip}",
        "vrrp_ip": "vrrp {vrid} ip {vip}",
        "vrrp_priority": "vrrp {vrid} priority {pri}",
        "mstp_region": "spanning-tree mst configuration\n name {name}\n instance {inst} vlan {vlans}",
        "mstp_instance": "spanning-tree mst {inst} root primary",
        "ospf_enable": "router ospf {pid}\n router-id {rid}",
        "ospf_network": "network {net} {wildcard} area {area}",
        "ospf_area": "area {area} stub",
        "policy_route": "route-map {name} permit {node}\n match ip address {num}\n set ip next-hop {next_hop}",
    },

    # --- Dcn (神州数码) - CLI similar to Cisco ---
    "Dcn": {
        "enter_config": "configure terminal",
        "hostname": "hostname {hostname}",
        "create_vlan": "vlan {vlans}",
        "interface": "interface {ifname}",
        "access_mode": "switchport mode access",
        "access_vlan": "switchport access vlan {vlan}",
        "trunk_mode": "switchport mode trunk",
        "trunk_allow": "switchport trunk allowed vlan {vlans}",
        "trunk_pvid": "switchport trunk native vlan {vlan}",
        "stp_enable": "spanning-tree",
        "stp_mode": "spanning-tree mode rstp",
        "stp_edge": "spanning-tree portfast",
        "mgmt_intf": "interface vlan {vlan}",
        "mgmt_ip": "ip address {ip} {mask}",
        "save": "copy running-config startup-config",
        "show": "show running-config",
        "lldp": "show lldp neighbors",
        # advanced switch
        "dhcp_enable": "service dhcp",
        "dhcp_pool": "ip dhcp pool {pool_name}",
        "dhcp_gateway": "default-router {gw}",
        "dhcp_dns": "dns-server {dns}",
        "dhcp_excluded": "ip dhcp excluded-address {start} {end}",
        "port_security": "switchport port-security",
        "port_security_max": "switchport port-security maximum {max}",
        "ip_source_guard": "ip verify source",
        "static_route": "ip route {dest} {mask} {next_hop}",
        "port_mirror": "monitor session 1 source interface {src} both\nmonitor session 1 destination interface {dst}",
        "acl_deny_subnet": "access-list {num} deny ip {src} {wildcard} {dst} {w_dst}",
        "acl_permit_tcp": "access-list {num} permit tcp {src} {wildcard} {dst} {w_dst} eq {port}",
        "acl_apply_in": "ip access-group {num} in",
        "vrrp_create": "vrrp {vrid} ip {vip}",
        "vrrp_ip": "vrrp {vrid} ip {vip}",
        "vrrp_priority": "vrrp {vrid} priority {pri}",
        "mstp_region": "spanning-tree mst configuration\n name {name}\n instance {inst} vlan {vlans}",
        "mstp_instance": "spanning-tree mst {inst} root primary",
        "ospf_enable": "router ospf {pid}\n router-id {rid}",
        "ospf_network": "network {net} {wildcard} area {area}",
        "ospf_area": "area {area} stub",
        "policy_route": "route-map {name} permit {node}\n match ip address {num}\n set ip next-hop {next_hop}",
    },
}


def _mask_to_prefix(mask: str) -> str:
    """Convert subnet mask to CIDR prefix length."""
    try:
        parts = mask.split(".")
        binary = "".join(format(int(p), "08b") for p in parts)
        return str(binary.count("1"))
    except Exception:
        return "24"


def _collect_topology_vlans(topology: dict) -> Set[int]:
    """Extract all VLAN IDs referenced in the topology links."""
    vlans = set()
    for link in topology.get("links", []):
        for vlan_field in ("accessVlan", "nativeVlan"):
            v = link.get(vlan_field)
            if v is not None and v != "":
                try:
                    vlans.add(int(v))
                except (ValueError, TypeError):
                    pass
        for v in link.get("allowedVlans", []) or []:
            try:
                vlans.add(int(v))
            except (ValueError, TypeError):
                pass
    return vlans


def _node_category(node: dict) -> str:
    """Determine device category from node data.

    Returns one of: 'router', 'firewall', 'switch', 'endpoint'.
    Checks both 'role' and 'category' fields, with 'role' taking priority.
    """
    role = (node.get("role") or "").lower()
    cat = (node.get("category") or "").lower()
    effective = role or cat
    if effective in ("router",):
        return "router"
    if effective in ("firewall", "security"):
        return "firewall"
    if effective in ("switch", "core", "access", "distribution", "aggregation"):
        return "switch"
    return "endpoint"


def _normalize_vendor_name(name: str) -> str:
    """Normalize a vendor name string to match exact _VENDOR_SYNTAX keys.

    Uses case-insensitive lookup instead of str.capitalize() which breaks
    multi-letter acronyms (e.g. 'H3C' -> 'H3c', 'HPE' -> 'Hpe').
    """
    name_lower = name.lower().strip()
    for known_key in _VENDOR_SYNTAX:
        if known_key.lower() == name_lower:
            return known_key
    # Last resort: title-case the input
    return name.strip().title()


def _resolve_vendor_key(base_vendor: str, node: dict, node_key: str = "") -> tuple:
    """Resolve the correct _VENDOR_SYNTAX key for a node, considering role.

    Args:
        base_vendor: The vendor name from the node's vendor field or global param.
        node: The topology node dict (has 'role' and/or 'category').
        node_key: Device key, used to attach generation warnings.

    Returns:
        (resolved_key, syntax_dict) tuple. Falls back to base vendor if no
        role-specific variant exists. If the base vendor has NO syntax table
        either, falls back to 'Huawei' AND records a loud warning — the
        generated config uses the wrong vendor's syntax and must be reviewed.
    """
    base_vendor = _normalize_vendor_name(base_vendor)
    node_cat = _node_category(node)

    # mapping: node category -> vendor suffix to try first
    role_suffix_map = {
        "router": "_router",
        "firewall": "_fw",
    }

    suffix = role_suffix_map.get(node_cat, "")
    if suffix:
        lookup = f"{base_vendor}{suffix}"
        if lookup in _VENDOR_SYNTAX:
            return lookup, _VENDOR_SYNTAX[lookup]

    # fall back to base vendor name
    if base_vendor in _VENDOR_SYNTAX:
        return base_vendor, _VENDOR_SYNTAX[base_vendor]

    # ultimate fallback — NOT silent anymore: 产出的是华为语法, 必须让用户知道
    _warn(node_key, f"厂商 '{base_vendor}' 没有语法模板, 已回退为 Huawei 语法生成! "
                    f"该设备配置可能完全不适用于真实设备, 请人工重写或先在 KB 中补充该厂商语法。")
    return "Huawei", _VENDOR_SYNTAX["Huawei"]


# ---- Per-role config generators ----

def _generate_acl_rules(
    node_key: str,
    node: dict,
    vendor_key: str,
    syntax: dict,
    device_links: dict,
    all_nodes: dict,
) -> list:
    """Generate ACL rules based on security zones in the topology.

    Rules generated (ACL 3000 series, deterministic per zone):
      - ACL 3001: External -> Internal deny (applied on external-facing interface)
      - ACL 3002: External -> DMZ permit tcp 80/443 (applied on external-facing interface)
      - ACL 3003: DMZ -> Internal deny (applied on DMZ-facing interface)

    If suitable peers with zone info are found, generates the matching rules.
    Returns empty list if no zone info available.
    """
    lines = []
    if not syntax.get("acl_deny_subnet"):
        return lines

    ZONE_MAP = {
        "dmz": "DMZ", "dmz区": "DMZ",
        "external": "External", "outside": "External", "untrust": "External",
        "外部": "External", "外网": "External", "外部网络": "External",
        "internal": "Internal", "inside": "Internal", "trust": "Internal",
        "内部": "Internal", "内网": "Internal", "内部网络": "Internal",
        "management": "Management", "管理": "Management", "管理区": "Management",
    }

    def classify_zone(n):
        z = (n.get("zone") or "").strip()
        zl = z.lower()
        for k, v in ZONE_MAP.items():
            if k in zl:
                return v
        return None

    # Discover zone members
    external_peers = []
    dmz_peers = []
    internal_peers = []

    for link in device_links.get(node_key, []):
        peer_key = link.get("to") if link.get("from") == node_key else link.get("from")
        peer = all_nodes.get(peer_key)
        if not peer:
            continue
        pz = classify_zone(peer)
        if pz == "External":
            external_peers.append(peer_key)
        elif pz == "DMZ":
            dmz_peers.append(peer_key)
        elif pz == "Internal":
            internal_peers.append(peer_key)

    node_zone = classify_zone(node)

    if not (external_peers or dmz_peers or internal_peers or node_zone):
        return lines

    lines.append(f"! --- ACL rules (zone-based) ---")

    acl_num = 3000
    is_juniper = vendor_key in ("Juniper",)

    # --- Rule 1: External -> Internal deny (ACL 3001) ---
    # Apply when this device faces External and has Internal peers
    if node_zone == "External" and internal_peers:
        acl_num += 1
        if is_juniper:
            lines.append(f"! ACL {acl_num}: deny ip 0.0.0.0/0 -> 192.168.0.0/16 (External->Internal)")
        elif syntax.get("acl_deny_subnet"):
            try:
                lines.append(syntax["acl_deny_subnet"].format(
                    num=acl_num, src="0.0.0.0", wildcard="255.255.255.255",
                    dst="192.168.0.0", w_dst="0.0.255.255"))
            except (KeyError, ValueError):
                lines.append(f"! ACL {acl_num}: deny ip any -> 192.168.0.0/16")

    # --- Rule 2: External -> DMZ permit tcp 80/443 (ACL 3002) ---
    # Apply when this device faces External and has DMZ peers
    if node_zone == "External" and dmz_peers:
        acl_num += 1
        if is_juniper:
            lines.append(f"! ACL {acl_num}: permit tcp 0.0.0.0/0 -> 172.16.0.0/16 eq 80,443 (External->DMZ)")
        elif syntax.get("acl_permit_tcp"):
            for port in ("80", "443"):
                try:
                    lines.append(syntax["acl_permit_tcp"].format(
                        num=acl_num, src="0.0.0.0", wildcard="255.255.255.255",
                        dst="172.16.0.0", w_dst="0.0.255.255", port=port))
                except (KeyError, ValueError):
                    pass
        else:
            lines.append(f"! ACL {acl_num}: permit tcp any -> 172.16.0.0/16 eq 80,443")

    # --- Rule 3: DMZ -> Internal deny (ACL 3003) ---
    # Apply when both DMZ and Internal peers exist (regardless of node's own zone)
    if dmz_peers and internal_peers and node_zone in ("External", "DMZ", "Internal"):
        acl_num += 1
        if is_juniper:
            lines.append(f"! ACL {acl_num}: deny ip 172.16.0.0/16 -> 192.168.0.0/16 (DMZ->Internal)")
        elif syntax.get("acl_deny_subnet"):
            try:
                lines.append(syntax["acl_deny_subnet"].format(
                    num=acl_num, src="172.16.0.0", wildcard="0.0.255.255",
                    dst="192.168.0.0", w_dst="0.0.255.255"))
            except (KeyError, ValueError):
                lines.append(f"! ACL {acl_num}: deny ip 172.16.0.0/16 -> 192.168.0.0/16")

    return lines


def _generate_ospf_config(
    node_key: str,
    node: dict,
    vendor_key: str,
    syntax: dict,
    all_vlans: Set[int],
) -> list:
    """Generate OSPF routing configuration for L3 switches and routers.

    - Router-ID: node.ospfRouterId → mgmtIp → auto from lowest VLAN gateway (192.168.{vlan}.1)
    - Area assignment: core/router = Area 0, aggregation = Area 1
    - Networks: one network statement per SVI subnet (192.168.{vlan}.0/24)
    """
    lines = []
    if not syntax.get("ospf_enable") or not syntax.get("ospf_network"):
        return lines

    node_role = node.get("role", "access")
    if node_role not in ("core", "aggregation", "router"):
        return lines

    non_default_vlans = {v for v in all_vlans if v != 1}
    if not non_default_vlans:
        return lines

    # Router-ID: explicit → mgmtIp → auto
    rid = node.get("ospfRouterId") or node.get("mgmtIp") or ""
    if not rid:
        min_vlan = min(non_default_vlans)
        rid = f"192.168.{min_vlan}.1"

    # Area assignment
    area = "0" if node_role in ("core", "router") else "1"

    ospf_pid = node.get("ospfPid") or 1

    lines.append(f"! --- OSPF routing (Area {area}) ---")

    # Enable OSPF with router-id
    if vendor_key in ("Juniper",):
        try:
            lines.append(syntax["ospf_enable"].format(area=area, ifname="lo0"))
        except (KeyError, ValueError):
            lines.append(syntax["ospf_enable"])
    elif vendor_key == "SONiC":
        try:
            lines.append(syntax["ospf_enable"].format(pid=ospf_pid, rid=rid))
        except (KeyError, ValueError):
            pass
    elif vendor_key in ("Extreme",):
        try:
            lines.append(syntax["ospf_enable"])
        except (KeyError, ValueError):
            pass
    else:
        try:
            lines.append(syntax["ospf_enable"].format(pid=ospf_pid, rid=rid))
        except (KeyError, ValueError):
            lines.append(syntax["ospf_enable"])

    # Network statements per VLAN
    for v in sorted(non_default_vlans):
        net = f"192.168.{v}.0"
        wildcard = "0.0.0.255"
        prefix = 24
        vlan_name = f"VLAN{v}"

        if vendor_key in ("Juniper",):
            try:
                lines.append(syntax["ospf_network"].format(
                    area=area, ifname=f"vlan.{v}"))
            except (KeyError, ValueError):
                pass
        elif vendor_key in ("Extreme",):
            try:
                lines.append(syntax["ospf_network"].format(
                    vlan_name=vlan_name, area=area))
            except (KeyError, ValueError):
                pass
        elif vendor_key in ("SONiC",):
            try:
                lines.append(syntax["ospf_network"].format(
                    net=net, prefix=prefix, area=area))
            except (KeyError, ValueError):
                pass
        elif vendor_key in ("Ruijie", "Cisco", "NSFocus", "Sangfor", "QiAnXin",
                          "Arista", "HPE", "ZTE", "Dell", "Maipu", "Hikvision",
                          "Tplink", "Fiberhome", "Dptecn", "Inspur", "Boda",
                          "Raisecom", "Dcn", "H3C", "Huawei"):
            # Cisco-like: `network 192.168.10.0 0.0.0.255 area 0`
            try:
                lines.append(syntax["ospf_network"].format(
                    net=net, wildcard=wildcard, area=area, pid=ospf_pid, rid=rid))
            except (KeyError, ValueError):
                lines.append(syntax["ospf_network"])
        else:
            try:
                lines.append(syntax["ospf_network"].format(
                    net=net, wildcard=wildcard, area=area, pid=ospf_pid, rid=rid))
            except (KeyError, ValueError):
                lines.append(syntax["ospf_network"])

    return lines


# ---- VRRP pair detection ----

def _detect_vrrp_pairs(topology: dict) -> dict:
    """Detect core/aggregation switch pairs suitable for VRRP.

    Returns: {node_key: {mode: 'master'|'standby', peer: peer_key, vlans: set}}
    """
    nodes = topology.get("nodes", {})
    links = topology.get("links", [])

    # Find all L3 switches (core, aggregation)
    l3_switches = {}
    for nk, nd in nodes.items():
        role = (nd.get("role") or "").lower()
        if role in ("core", "aggregation"):
            l3_switches[nk] = nd

    if len(l3_switches) < 2:
        return {}

    # Find direct links between L3 switches
    pairs = {}
    for nk_a in l3_switches:
        for nk_b in l3_switches:
            if nk_a >= nk_b:
                continue
            # Check for direct link
            for link in links:
                f = link.get("from", "")
                t = link.get("to", "")
                if (f == nk_a and t == nk_b) or (f == nk_b and t == nk_a):
                    # Collect shared VLANs from trunk
                    vlans = set()
                    if link.get("accessVlan"):
                        vlans.add(link["accessVlan"])
                    for v in (link.get("allowedVlans") or []):
                        vi = int(v) if isinstance(v, str) else v
                        if not isinstance(vi, bool):
                            vlans.add(vi)
                    vlan_str = link.get("vlan") or ""
                    if vlan_str:
                        for p in str(vlan_str).split(","):
                            try:
                                vlans.add(int(p.strip()))
                            except ValueError:
                                pass

                    if vlans:
                        # Assign master/standby by key ordering
                        master = nk_a if nk_a < nk_b else nk_b
                        standby = nk_b if master == nk_a else nk_a
                        pairs[master] = {"mode": "master", "peer": standby, "vlans": vlans}
                        pairs[standby] = {"mode": "standby", "peer": master, "vlans": vlans}
                    break

    return pairs


def _generate_vrrp_config(
    node_key: str,
    node: dict,
    vendor_key: str,
    syntax: dict,
    vrrp_pairs: dict,
    all_vlans: Set[int],
) -> list:
    """Generate VRRP configuration for a switch that is part of a VRRP pair.

    Master: priority 120 + preempt
    Standby: priority 100
    VRID = VLAN ID
    Virtual IP = gateway IP (192.168.{vlan}.1)
    """
    lines = []
    if node_key not in vrrp_pairs:
        return lines
    if not syntax.get("vrrp_create"):
        return lines

    pair_info = vrrp_pairs[node_key]
    mode = pair_info["mode"]
    shared_vlans = pair_info["vlans"] & all_vlans
    if not shared_vlans:
        return lines

    lines.append(f"! --- VRRP ({mode}, peer: {pair_info['peer']}) ---")

    priority = 120 if mode == "master" else 100

    for vlan in sorted(shared_vlans):
        if vlan == 1:
            continue
        vrid = vlan
        vip = f"192.168.{vlan}.1"

        if vendor_key in ("Juniper",):
            ifname = f"vlan.{vlan}"
            try:
                lines.append(syntax["vrrp_create"].format(
                    vrid=vrid, vip=vip, ifname=ifname, ip=vip, prefix=24))
            except (KeyError, ValueError):
                pass
            try:
                lines.append(syntax["vrrp_priority"].format(
                    vrid=vrid, pri=priority, ifname=ifname, ip=vip, prefix=24))
            except (KeyError, ValueError):
                pass
        else:
            try:
                lines.append(syntax["vrrp_create"].format(vrid=vrid, vip=vip))
            except (KeyError, ValueError):
                pass
            try:
                lines.append(syntax["vrrp_priority"].format(vrid=vrid, pri=priority))
            except (KeyError, ValueError):
                pass

        # Add preempt for master
        if mode == "master" and syntax.get("vrrp_create"):
            if vendor_key in ("Huawei", "H3C"):
                lines.append(f"  vrrp vrid {vrid} preempt-mode timer delay 30")

    return lines


def _generate_switch_config(
    node_key: str,
    node: dict,
    hostname: str,
    vendor_key: str,
    syntax: dict,
    device_links: dict,
    all_vlans: Set[int],
    global_settings: dict = None,
    all_nodes: dict = None,
    vrrp_pairs: dict = None,
) -> list:
    """Generate configuration lines for a switch (access/aggregation/core).

    Covers: hostname, VLAN creation, STP, interface mode/VLAN, port-security,
    management IP, DHCP, static routes, VRRP, MSTP, OSPF, and save.
    """
    lines = []

    # Filter out default VLAN 1 from batch creation
    non_default_vlans = {v for v in all_vlans if v != 1}

    # --- Header ---
    lines.append(f"! --- {hostname} ({vendor_key} switch -- auto-generated) ---")

    # --- Enter config mode ---
    if syntax.get("enter_config"):
        lines.append(syntax["enter_config"])

    # --- Hostname ---
    if syntax.get("hostname"):
        try:
            lines.append(syntax["hostname"].format(hostname=hostname))
        except (KeyError, ValueError):
            lines.append(syntax["hostname"])

    # --- NTP / SNMP / AAA (global settings) ---
    gs = global_settings or {}
    if gs:
        ntp_server = gs.get("ntpServers", "")
        snmp_community = gs.get("snmpCommunity", "")
        admin_user = gs.get("adminUser", "")
        admin_password = gs.get("adminPassword", "")
        domain_name = gs.get("domainName", "")

        if domain_name and syntax.get("domain_name"):
            try:
                lines.append(syntax["domain_name"].format(domain=domain_name))
            except (KeyError, ValueError):
                lines.append(f"! domain name {domain_name}")

        if ntp_server and syntax.get("ntp_server"):
            try:
                for ns in ntp_server.replace(" ", "").split(","):
                    if ns.strip():
                        lines.append(syntax["ntp_server"].format(ip=ns.strip()))
            except (KeyError, ValueError):
                lines.append(f"! ntp-server {ntp_server}")
        elif ntp_server:
            lines.append(f"! NTP server not configured (vendor '{vendor_key}' missing ntp_server template)")

        if snmp_community and syntax.get("snmp_community"):
            try:
                lines.append(syntax["snmp_community"].format(community=snmp_community))
            except (KeyError, ValueError):
                lines.append(f"! snmp community {snmp_community}")
        elif snmp_community:
            lines.append(f"! SNMP community not configured (vendor '{vendor_key}' missing snmp_community template)")

        if admin_user and admin_password and syntax.get("aaa_local_user"):
            try:
                lines.append(syntax["aaa_local_user"].format(user=admin_user, pwd=admin_password))
            except (KeyError, ValueError):
                lines.append(f"! aaa local-user {admin_user}")
        elif admin_user:
            lines.append(f"! AAA local user not configured (vendor '{vendor_key}' missing aaa_local_user template)")

    # --- VLAN creation ---
    vlan_str = " ".join(str(v) for v in sorted(non_default_vlans)) if non_default_vlans else ""
    if non_default_vlans:
        if vendor_key in ("Juniper",):
            for v in sorted(non_default_vlans):
                try:
                    lines.append(syntax["create_vlan"].format(vlan=v, vlan_name=f"VLAN{v}"))
                except (KeyError, ValueError):
                    lines.append(syntax["create_vlan"])
        elif vendor_key in ("Extreme",):
            for v in sorted(non_default_vlans):
                try:
                    lines.append(syntax["create_vlan"].format(vlan=v, vlan_name=f"VLAN{v}"))
                except (KeyError, ValueError):
                    pass
        elif vendor_key in ("Sonic",):
            for v in sorted(non_default_vlans):
                try:
                    lines.append(syntax["create_vlan"].format(vlan=v))
                except (KeyError, ValueError):
                    pass
        else:
            try:
                lines.append(syntax["create_vlan"].format(vlans=vlan_str))
            except (KeyError, ValueError):
                lines.append(syntax["create_vlan"])

    # --- STP global ---
    if syntax.get("stp_enable"):
        stp_tmpl = syntax["stp_enable"]
        if "{vlans}" in stp_tmpl:
            try:
                lines.append(stp_tmpl.format(vlans=vlan_str))
            except (KeyError, ValueError):
                lines.append(stp_tmpl)
        else:
            lines.append(stp_tmpl)
        if syntax.get("stp_mode"):
            lines.append(syntax["stp_mode"])

    # --- DHCP global enable ---
    dhcp_tmpl = syntax.get("dhcp_enable", "")
    if dhcp_tmpl and vendor_key not in ("Sonic", "Extreme"):
        # Skip if template requires variables we don't have at global scope
        if "{" not in dhcp_tmpl:
            lines.append(dhcp_tmpl)

    # --- SVI (VLAN interface) & DHCP pool generation ---
    node_role = node.get("role", "access")
    is_l3_switch = node_role in ("core", "aggregation")
    svi_subnet_prefix = 24

    if is_l3_switch and non_default_vlans:
        cc = _comment_char(vendor_key)
        for v in sorted(non_default_vlans):
            gw = f"192.168.{v}.1"
            subnet_mask = "255.255.255.0"
            prefix = svi_subnet_prefix
            ctx = _vlan_ctx(v, gw, subnet_mask, prefix)
            lines.append(f"! --- VLAN {v} gateway ---")

            # SVI interface
            if syntax.get("mgmt_intf"):
                s = _fmt(syntax["mgmt_intf"], ctx)
                if s is not None:
                    lines.append(s)
                else:
                    lines.append(cc + f" WARNING: 厂商 {vendor_key} mgmt_intf 模板占位符与上下文不匹配, VLAN {v} 的 SVI 接口未生成!")
                    _warn(node_key, f"mgmt_intf 模板占位符不匹配, VLAN {v} SVI 接口行缺失")
            if syntax.get("mgmt_ip"):
                s = _fmt(syntax["mgmt_ip"], ctx)
                if s is not None:
                    lines.append(s)
                else:
                    lines.append(cc + f" WARNING: 厂商 {vendor_key} mgmt_ip 模板占位符与上下文不匹配, VLAN {v} 的网关 IP 未配置!")
                    _warn(node_key, f"mgmt_ip 模板占位符不匹配, VLAN {v} 网关 IP 行缺失")

            # DHCP pool for this VLAN
            if syntax.get("dhcp_pool") and syntax.get("dhcp_enable"):
                try:
                    lines.append(syntax["dhcp_pool"].format(**ctx))
                except (KeyError, ValueError):
                    lines.append(cc + f" WARNING: 厂商 {vendor_key} dhcp_pool 模板占位符不匹配, VLAN {v} 的 DHCP 地址池未生成!")
                    _warn(node_key, f"dhcp_pool 模板占位符不匹配, VLAN {v} DHCP 地址池缺失")
                for key, desc in (("dhcp_gateway", "DHCP 网关"), ("dhcp_dns", "DHCP DNS"),
                                  ("dhcp_excluded", "网关地址排除")):
                    if syntax.get(key):
                        try:
                            lines.append(syntax[key].format(**ctx))
                        except (KeyError, ValueError):
                            lines.append(cc + f" WARNING: 厂商 {vendor_key} {key} 模板占位符不匹配, VLAN {v} {desc}未配置!")
                            _warn(node_key, f"{key} 模板占位符不匹配, VLAN {v} {desc}行缺失")

    # --- Eth-Trunk / Link Aggregation ---
    # Collect bonded links and generate Eth-Trunk config blocks
    eth_trunk_seen = set()
    eth_trunk_member_ports = set()  # ports that are part of an Eth-Trunk (skip individual config)
    for link in device_links.get(node_key, []):
        if not link.get("bonded") or not link.get("ethTrunkId"):
            continue
        trid = link["ethTrunkId"]
        if trid in eth_trunk_seen:
            continue
        eth_trunk_seen.add(trid)
        is_from = (link.get("from") == node_key)
        member_ports = link.get("memberPortsFrom" if is_from else "memberPortsTo") or []
        # Mark member ports to skip standalone interface config
        for mp in member_ports:
            eth_trunk_member_ports.add(mp)

        if not syntax.get("eth_trunk_create"):
            continue

        # Create Eth-Trunk interface
        try:
            lines.append(syntax["eth_trunk_create"].format(id=trid))
        except (KeyError, ValueError):
            pass

        # LACP mode
        lacp_mode = link.get("lacpMode", "static")
        if syntax.get("lacp_enable"):
            try:
                lines.append(syntax["lacp_enable"])
            except (KeyError, ValueError):
                pass

        # Load balancing
        lb_mode = link.get("loadBalance", "src-dst-ip")
        if syntax.get("eth_trunk_load_bal"):
            try:
                lines.append(syntax["eth_trunk_load_bal"].format(mode=lb_mode))
            except (KeyError, ValueError):
                pass

        # Add member ports
        for mp in member_ports:
            if syntax.get("eth_trunk_member"):
                try:
                    lines.append(syntax["eth_trunk_member"].format(id=trid))
                except (KeyError, ValueError):
                    pass
            # Also enter physical interface and apply Eth-Trunk membership
            if syntax.get("interface"):
                try:
                    # Build physical interface name
                    if vendor_key in ("Juniper",):
                        ifname = mp.lower().replace("/", "-")
                    elif vendor_key in ("SONiC", "Sonic"):
                        ifname = mp
                    else:
                        ifname = mp
                    lines.append(syntax["interface"].format(ifname=ifname))
                except (KeyError, ValueError):
                    pass
            if syntax.get("eth_trunk_member"):
                try:
                    lines.append(syntax["eth_trunk_member"].format(id=trid))
                except (KeyError, ValueError):
                    pass

        # VLAN config on Eth-Trunk interface
        if syntax.get("trunk_mode"):
            try:
                lines.append(syntax["trunk_mode"])
            except (KeyError, ValueError):
                pass
        if syntax.get("trunk_allow"):
            allowed = link.get("allowedVlans", [])
            if allowed:
                sep = "," if vendor_key in ("Cisco",) else " "
                try:
                    lines.append(syntax["trunk_allow"].format(vlans=sep.join(str(v) for v in allowed)))
                except (KeyError, ValueError):
                    pass
        if syntax.get("trunk_pvid"):
            native = link.get("nativeVlan")
            if native:
                try:
                    lines.append(syntax["trunk_pvid"].format(vlan=native))
                except (KeyError, ValueError):
                    pass

    # --- Interface config from topology links ---
    for link in device_links.get(node_key, []):
        # Determine which end of the link this device is
        is_from = (link.get("from") == node_key)
        port = link.get("fromPort" if is_from else "toPort") or "?"

        # Build interface name
        if vendor_key in ("Juniper",):
            ifname = port.lower().replace("/", "-") if port else "ge-0/0/0"
        elif vendor_key in ("SONiC", "Sonic"):
            ifname = port if port else "Ethernet0"
        elif vendor_key in ("Extreme",):
            ifname = port if port else "1"
        else:
            ifname = port if port else "GigabitEthernet0/0/1"

        # Interface header
        if syntax.get("interface"):
            try:
                lines.append(syntax["interface"].format(ifname=ifname))
            except (KeyError, ValueError):
                pass

        mode = link.get("mode", "access")
        if mode == "trunk":
            # Trunk config
            if syntax.get("trunk_mode"):
                tmpl = syntax["trunk_mode"]
                if vendor_key in ("Extreme",):
                    allowed = link.get("allowedVlans", [])
                    for av in (allowed or []):
                        try:
                            lines.append(syntax["trunk_mode"].format(ifname=ifname, vlan_name=f"VLAN{av}", vlan=av))
                        except (KeyError, ValueError):
                            pass
                elif vendor_key in ("Sonic",):
                    allowed = link.get("allowedVlans", [])
                    for av in (allowed or []):
                        try:
                            lines.append(syntax["trunk_mode"].format(ifname=ifname, vlan=av))
                        except (KeyError, ValueError):
                            pass
                elif vendor_key in ("Juniper",):
                    try:
                        lines.append(tmpl.format(ifname=ifname))
                    except (KeyError, ValueError):
                        pass
                    allowed = link.get("allowedVlans", [])
                    if allowed:
                        vlan_names = " ".join(f"VLAN{v}" for v in allowed)
                        try:
                            ta = syntax["trunk_allow"].format(ifname=ifname, vlans=" ".join(str(v) for v in allowed), vlans_list=vlan_names)
                            lines.append(ta)
                        except (KeyError, ValueError):
                            pass
                else:
                    try:
                        native_vlan = link.get("nativeVlan", 1)
                        if "{vlan}" in tmpl:
                            lines.append(tmpl.format(vlan=native_vlan))
                        else:
                            lines.append(tmpl)
                    except (KeyError, ValueError):
                        lines.append(tmpl)

            if syntax.get("trunk_allow") and vendor_key not in ("Extreme", "Sonic", "Juniper"):
                allowed = link.get("allowedVlans", [])
                if allowed:
                    sep = "," if vendor_key in ("Cisco",) else " "
                    try:
                        lines.append(syntax["trunk_allow"].format(vlans=sep.join(str(v) for v in allowed)))
                    except (KeyError, ValueError):
                        pass

            if syntax.get("trunk_pvid") and vendor_key not in ("Extreme", "Sonic"):
                native = link.get("nativeVlan")
                if native:
                    try:
                        lines.append(syntax["trunk_pvid"].format(vlan=native))
                    except (KeyError, ValueError):
                        pass
        else:
            # Access config
            access_vlan = link.get("accessVlan", link.get("nativeVlan", 1))
            if syntax.get("access_mode"):
                am = syntax["access_mode"]
                if vendor_key in ("Extreme",):
                    try:
                        lines.append(am.format(ifname=ifname, vlan_name=f"VLAN{access_vlan}", vlan=access_vlan))
                    except (KeyError, ValueError):
                        pass
                elif vendor_key in ("Sonic",):
                    try:
                        lines.append(am.format(ifname=ifname, vlan=access_vlan))
                    except (KeyError, ValueError):
                        pass
                elif vendor_key in ("HPE",):
                    try:
                        lines.append(am.format(vlan=access_vlan))
                    except (KeyError, ValueError):
                        pass
                elif vendor_key in ("Juniper",):
                    try:
                        lines.append(am.format(ifname=ifname))
                    except (KeyError, ValueError):
                        pass
                else:
                    lines.append(am)

            if syntax.get("access_vlan") and vendor_key not in ("HPE", "Extreme", "Sonic"):
                try:
                    lines.append(syntax["access_vlan"].format(vlan=access_vlan, ifname=ifname))
                except (KeyError, ValueError):
                    pass

            # Port-security on access ports
            if syntax.get("port_security"):
                try:
                    if "{" not in syntax["port_security"]:
                        lines.append(syntax["port_security"])
                    else:
                        lines.append(syntax["port_security"].format(ifname=ifname))
                except (KeyError, ValueError):
                    pass

        # STP edge for access ports
        if mode == "access" and syntax.get("stp_edge"):
            tmpl = syntax["stp_edge"]
            if "{ifname}" in tmpl:
                try:
                    lines.append(tmpl.format(ifname=ifname))
                except (KeyError, ValueError):
                    pass
            else:
                lines.append(tmpl)

    # --- Management IP ---
    mgmt_ip = node.get("mgmtIp")
    mgmt_vlan = node.get("mgmtVlan")
    if mgmt_ip and mgmt_vlan:
        if syntax.get("mgmt_intf"):
            try:
                lines.append(syntax["mgmt_intf"].format(vlan=mgmt_vlan, vlan_name=f"VLAN{mgmt_vlan}"))
            except (KeyError, ValueError):
                pass
        if syntax.get("mgmt_ip"):
            mask = "255.255.255.0"
            if "/" in str(mgmt_ip):
                parts = str(mgmt_ip).split("/")
                ip = parts[0]
                prefix = parts[1]
            else:
                ip = str(mgmt_ip)
                prefix = "24"
            try:
                lines.append(syntax["mgmt_ip"].format(ip=ip, mask=mask, vlan=mgmt_vlan, prefix=prefix))
            except (KeyError, ValueError):
                pass

    # --- VRRP redundancy ---
    if vrrp_pairs and node_key in vrrp_pairs:
        vrrp_lines = _generate_vrrp_config(
            node_key, node, vendor_key, syntax, vrrp_pairs, all_vlans,
        )
        if vrrp_lines:
            lines.extend(vrrp_lines)

    # --- OSPF routing (L3 devices) ---
    node_role = node.get("role", "access")
    if node_role in ("core", "aggregation", "router"):
        ospf_lines = _generate_ospf_config(
            node_key, node, vendor_key, syntax, all_vlans,
        )
        if ospf_lines:
            lines.extend(ospf_lines)

    # --- Footer / save ---
    if syntax.get("save"):
        if vendor_key in ("Juniper",):
            lines.append("commit")
        elif vendor_key in ("Extreme",):
            lines.append(syntax["save"])
        elif vendor_key in ("Sonic",):
            lines.append(syntax["save"])
        elif vendor_key in ("Cisco",):
            lines.append("end")
            lines.append(syntax["save"])
        elif vendor_key in ("Huawei", "H3C", "Huawei_router", "H3C_router", "Huawei_fw", "H3C_fw",
                           "Maipu", "Fiberhome"):
            lines.append("return")
            lines.append(syntax["save"])
        else:
            lines.append("end")
            lines.append(syntax["save"])

    return lines


def _generate_router_config(
    node_key: str,
    node: dict,
    hostname: str,
    vendor_key: str,
    syntax: dict,
    device_links: dict,
    all_vlans: Set[int],
    global_settings: dict = None,
    all_nodes: dict = None,
    vrrp_pairs: dict = None,
) -> list:
    """Generate configuration lines for a router.

    Extends switch config with WAN interfaces, NAT, and advanced routing.
    """
    # Start with the standard switch/LAN-side config
    lines = _generate_switch_config(
        node_key, node, hostname, vendor_key, syntax,
        device_links, all_vlans, global_settings, all_nodes, vrrp_pairs,
    )

    # Fix the header comment
    if lines and lines[0].startswith("! ---"):
        lines[0] = lines[0].replace(" switch ", " router ")

    # --- Router-specific WAN / NAT section ---
    wan_config = node.get("wanConfig") or {}

    # Determine WAN mode from node data
    wan_mode = wan_config.get("mode") or node.get("wanMode") or "static"

    # Insert WAN section before the save/footer block (which is at the end)
    # Find insertion point (before "end" / "return" / save commands)
    insert_idx = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        l = lines[i].strip()
        if l in ("end", "return", "commit") or l.startswith("copy ") or l.startswith("write ") or l.startswith("save"):
            insert_idx = i
        else:
            break

    wan_lines = []

    if wan_mode == "pppoe" and syntax.get("wan_pppoe"):
        pppoe_user = wan_config.get("pppoeUser") or "pppoe-user"
        pppoe_pwd = wan_config.get("pppoePassword") or "pppoe-password"
        wan_lines.append(f"! --- WAN (PPPoE) ---")
        try:
            wan_lines.append(syntax["wan_pppoe"].format(user=pppoe_user, pwd=pppoe_pwd))
        except (KeyError, ValueError):
            wan_lines.append(syntax["wan_pppoe"])
    elif wan_mode == "dhcp" and syntax.get("wan_dhcp"):
        wan_lines.append(f"! --- WAN (DHCP client) ---")
        try:
            wan_lines.append(syntax["wan_dhcp"])
        except (KeyError, ValueError):
            pass
    elif syntax.get("wan_static_ip"):
        wan_lines.append(f"! --- WAN (Static IP) ---")
        wan_ip = wan_config.get("ip") or node.get("wanIp") or "203.0.113.10"
        wan_mask = wan_config.get("mask") or node.get("wanMask") or "255.255.255.252"
        try:
            wan_lines.append(syntax["wan_static_ip"].format(ip=wan_ip, mask=wan_mask))
        except (KeyError, ValueError):
            pass

    # NAT outbound (PAT)
    if syntax.get("nat_outbound") and wan_mode in ("pppoe", "static", "dhcp"):
        wan_lines.append(f"! --- NAT outbound (PAT) ---")
        try:
            wan_lines.append(syntax["nat_outbound"].format(acl_num=2000))
        except (KeyError, ValueError):
            pass

    # NAT server (port forwarding) entries
    nat_servers = wan_config.get("natServers") or node.get("natServers") or []
    if syntax.get("nat_server") and nat_servers:
        wan_lines.append(f"! --- NAT server (port forwarding) ---")
        for ns in nat_servers:
            try:
                wan_lines.append(syntax["nat_server"].format(
                    name=ns.get("name", "NAT-Server"),
                    public_ip=ns.get("publicIp", "203.0.113.10"),
                    public_port=ns.get("publicPort", 80),
                    private_ip=ns.get("privateIp", "192.168.1.1"),
                    private_port=ns.get("privatePort", 80),
                ))
            except (KeyError, ValueError):
                pass

    # Multi-ISP static routes
    isp_routes = wan_config.get("ispRoutes") or node.get("ispRoutes") or []
    if syntax.get("multi_isp_route") and isp_routes:
        wan_lines.append(f"! --- Multi-ISP static routes ---")
        for r in isp_routes:
            try:
                wan_lines.append(syntax["multi_isp_route"].format(
                    dest=r.get("dest", "0.0.0.0"),
                    mask=r.get("mask", "0.0.0.0"),
                    isp1_gw=r.get("isp1Gw", ""),
                    isp2_gw=r.get("isp2Gw", ""),
                ))
            except (KeyError, ValueError):
                pass

    # --- ACL rules (zone-based) ---
    if all_nodes:
        acl_lines = _generate_acl_rules(node_key, node, vendor_key, syntax, device_links, all_nodes)
        if acl_lines:
            wan_lines.extend(acl_lines)

    if wan_lines:
        # Insert WAN lines before the footer
        lines = lines[:insert_idx] + wan_lines + lines[insert_idx:]

    return lines


def _generate_firewall_config(
    node_key: str,
    node: dict,
    hostname: str,
    vendor_key: str,
    syntax: dict,
    device_links: dict,
    all_vlans: Set[int],
    global_settings: dict = None,
    all_nodes: dict = None,
    vrrp_pairs: dict = None,
) -> list:
    """Generate configuration lines for a firewall / security appliance.

    Extends switch config with security zones, interzone policies, and NAT.
    """
    # Start with switch config as the base
    lines = _generate_switch_config(
        node_key, node, hostname, vendor_key, syntax,
        device_links, all_vlans, global_settings, all_nodes, vrrp_pairs,
    )

    # Fix the header comment
    if lines and lines[0].startswith("! ---"):
        lines[0] = lines[0].replace(" switch ", " firewall ")

    # Find insertion point (before save/footer)
    insert_idx = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        l = lines[i].strip()
        if l in ("end", "return", "commit") or l.startswith("copy ") or l.startswith("write ") or l.startswith("save"):
            insert_idx = i
        else:
            break

    fw_lines = []
    fw_config = node.get("fwConfig") or {}

    # --- Security zones ---
    zones = fw_config.get("zones") or node.get("securityZones") or [
        {"name": "Trust", "priority": 5},
        {"name": "Untrust", "priority": 1},
        {"name": "DMZ", "priority": 3},
    ]
    if syntax.get("zone_create"):
        fw_lines.append(f"! --- Security zones ---")
        for z in zones:
            try:
                fw_lines.append(syntax["zone_create"].format(
                    zone=z.get("name", "Trust"),
                    pri=z.get("priority", 5),
                ))
            except (KeyError, ValueError):
                pass

    # Add interfaces to zones
    if syntax.get("zone_add_intf"):
        fw_lines.append(f"! --- Zone interface assignment ---")
        for link in device_links.get(node_key, []):
            is_from = (link.get("from") == node_key)
            port = link.get("fromPort" if is_from else "toPort") or "?"
            if vendor_key in ("Juniper",):
                ifname = port.lower().replace("/", "-") if port else "ge-0/0/0"
            elif vendor_key in ("Sonic",):
                ifname = port if port else "Ethernet0"
            else:
                ifname = port if port else "GigabitEthernet0/0/1"
            # Default interfaces to Untrust zone; override per config
            zone_name = "Untrust"
            try:
                fw_lines.append(syntax["zone_add_intf"].format(zone=zone_name, ifname=ifname))
            except (KeyError, ValueError):
                pass

    # --- Interzone policy ---
    if syntax.get("interzone_policy"):
        fw_lines.append(f"! --- Interzone policy ---")
        # Default policy: Trust -> Untrust permit
        try:
            fw_lines.append(syntax["interzone_policy"].format(
                src_zone="Trust",
                dst_zone="Untrust",
                dir="outbound",
                num=10,
                src_addr="192.168.0.0 0.0.255.255",
                dst_addr="any",
                name="Trust-to-Untrust",
            ))
        except (KeyError, ValueError):
            pass

    # --- FW NAT outbound ---
    if syntax.get("fw_nat_outbound"):
        fw_lines.append(f"! --- NAT outbound ---")
        try:
            fw_lines.append(syntax["fw_nat_outbound"].format(
                name="SNAT-Trust-Untrust",
                zone="Trust",
                dst_zone="Untrust",
            ))
        except (KeyError, ValueError):
            pass

    # --- FW NAT server (destination NAT) ---
    nat_servers = fw_config.get("natServers") or node.get("natServers") or []
    if syntax.get("fw_nat_server") and nat_servers:
        fw_lines.append(f"! --- Destination NAT (port mapping) ---")
        for ns in nat_servers:
            try:
                fw_lines.append(syntax["fw_nat_server"].format(
                    name=ns.get("name", "DNAT"),
                    public_ip=ns.get("publicIp", "203.0.113.10"),
                    public_port=ns.get("publicPort", 443),
                    private_ip=ns.get("privateIp", "192.168.1.10"),
                    private_port=ns.get("privatePort", 443),
                ))
            except (KeyError, ValueError):
                pass

    # --- WAN PPPoE / static ---
    wan_mode = (fw_config.get("wanMode") or node.get("wanMode") or "static")
    if wan_mode == "pppoe" and syntax.get("fw_pppoe"):
        fw_lines.append(f"! --- WAN (PPPoE) ---")
        try:
            fw_lines.append(syntax["fw_pppoe"].format(
                user=fw_config.get("pppoeUser", "pppoe-user"),
                pwd=fw_config.get("pppoePassword", "pppoe-password"),
            ))
        except (KeyError, ValueError):
            pass
    elif wan_mode == "static" and syntax.get("fw_static_ip"):
        fw_lines.append(f"! --- WAN (Static IP) ---")
        wan_ip = fw_config.get("wanIp") or "203.0.113.10"
        wan_mask = fw_config.get("wanMask") or "255.255.255.252"
        try:
            fw_lines.append(syntax["fw_static_ip"].format(ip=wan_ip, mask=wan_mask))
        except (KeyError, ValueError):
            pass

    # --- ACL rules (zone-based) ---
    if all_nodes:
        acl_lines = _generate_acl_rules(node_key, node, vendor_key, syntax, device_links, all_nodes)
        if acl_lines:
            fw_lines.extend(acl_lines)

    if fw_lines:
        lines = lines[:insert_idx] + fw_lines + lines[insert_idx:]

    return lines


def _generate_endpoint_config(
    node_key: str,
    node: dict,
    all_vlans: Set[int],
) -> list:
    """Generate a placeholder configuration block for endpoint / terminal devices."""
    lines = [f"! --- {node.get('hostname') or node.get('label') or node_key} (endpoint) ---"]
    lines.append(f"! Terminal device -- no L2/L3 switch configuration required.")
    if all_vlans:
        lines.append(f"! Associated VLAN(s): {', '.join(str(v) for v in sorted(all_vlans))}")
    else:
        lines.append(f"! Associated VLAN(s): N/A")
    return lines


def generate_config_from_kb(topology: dict, vendor: str, global_settings: dict = None) -> dict:
    """Generate device configurations using KB templates (no AI required).

    Branches by device role:
      - 'router':          _generate_router_config()
      - 'firewall'/'security': _generate_firewall_config()
      - 'switch'/'core'/'access'/'distribution': _generate_switch_config()
      - 'endpoint':        placeholder

    Vendor resolution:
      For each node, the vendor name is taken from node['vendor'] if present,
      otherwise the global *vendor* parameter. Role-specific vendor variants
      (e.g., 'Huawei_router', 'H3C_fw') are tried first and fall back to the
      base vendor name.

    Returns a dict keyed by device key, each value is a list of config command
    strings.
    """
    nodes = topology.get("nodes", {})
    links = topology.get("links", [])
    all_vlans = _collect_topology_vlans(topology)

    # 每次生成前清空上一轮的告警
    _GEN_WARNINGS.clear()

    # Build device -> links map for interface config generation
    device_links = {}
    for link_data in links:
        fk = link_data.get("from")
        tk = link_data.get("to")
        if fk:
            device_links.setdefault(fk, []).append(link_data)
        if tk:
            device_links.setdefault(tk, []).append(link_data)

    # Detect VRRP pairs (core/agg switches with direct trunk links)
    vrrp_pairs = _detect_vrrp_pairs(topology)

    configs = {}

    for node_key, node in nodes.items():
        hostname = node.get("hostname") or node.get("label") or node_key
        node_cat = _node_category(node)

        # Determine base vendor: node-level override takes priority
        node_vendor = node.get("vendor") or vendor
        vendor_key, syntax = _resolve_vendor_key(node_vendor, node, node_key)

        # ---- Endpoint: placeholder ----
        if node_cat == "endpoint":
            configs[node_key] = _generate_endpoint_config(node_key, node, all_vlans)
            continue

        # ---- Router ----
        if node_cat == "router":
            configs[node_key] = _generate_router_config(
                node_key, node, hostname, vendor_key, syntax,
                device_links, all_vlans, global_settings, nodes, vrrp_pairs,
            )
            continue

        # ---- Firewall / Security appliance ----
        if node_cat == "firewall":
            configs[node_key] = _generate_firewall_config(
                node_key, node, hostname, vendor_key, syntax,
                device_links, all_vlans, global_settings, nodes, vrrp_pairs,
            )
            continue

        # ---- Switch (core / access / distribution / generic switch) ----
        configs[node_key] = _generate_switch_config(
            node_key, node, hostname, vendor_key, syntax,
            device_links, all_vlans, global_settings, nodes, vrrp_pairs,
        )

    # 生成完毕: 把该设备的告警以注释行注入配置开头 (生成过程中已逐条 _warn)
    for dev_key, cfg_lines in configs.items():
        if isinstance(cfg_lines, list) and _GEN_WARNINGS.get(dev_key):
            cc = "!" if not cfg_lines or not str(cfg_lines[0]).startswith("#") else "#"
            configs[dev_key] = _warn_lines(dev_key, cc) + list(cfg_lines)

    return configs
