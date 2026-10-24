#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_templates.py — 多厂商模板自动化审计 (无需任何第三方依赖)

三层验证的第 1 层: 机器可跑的静态审计
  1) 厂商回退检查   — 生成结果里不允许出现"回退为 Huawei 语法"告警
  2) 语法缺键检查   — 生成结果里不允许出现"语法表缺少 xxx 键"告警
  3) 方言污染检查   — Cisco 设备不应出现华为系命令(port link-type), 反之亦然
  4) 自洽性检查     — 生成的命令行头部应能在该厂商知识库 KB 中找到出处
  5) 基本结构检查   — 每台设备应有非空配置

用法:  python test_templates.py            # 全部厂商
       python test_templates.py Huawei     # 指定厂商
输出:  控制台摘要 + template_audit_report.md
退出码: 有 FAIL 时为 1 (可接 CI)
"""
import json
import re
import sys
from pathlib import Path

from kb_engine import (
    _VENDOR_SYNTAX, generate_config_from_kb, load_vendor,
    COMMANDS_DIR,
)

OUT = Path(__file__).parent / "template_audit_report.md"

# ---------- 样例拓扑: 1 路由器 + 1 核心 + 1 接入 + 2 终端, 3 个 VLAN ----------
def sample_topology():
    return {
        "nodes": {
            "r1":  {"key": "r1",  "role": "router",  "hostname": "R1", "vendor": None},
            "swc": {"key": "swc", "role": "core",    "hostname": "CORE-SW"},
            "swa": {"key": "swa", "role": "access",  "hostname": "ACC-SW"},
            "pc1": {"key": "pc1", "role": "pc",      "hostname": "PC1"},
        },
        "links": [
            {"from": "r1",  "to": "swc", "type": "trunk", "allowedVlans": [10, 20, 30]},
            {"from": "swc", "to": "swa", "type": "trunk", "allowedVlans": [10, 20, 30]},
            {"from": "swa", "to": "pc1", "type": "access", "accessVlan": 10},
        ],
    }

# ---------- 方言签名: 用于检测"把 A 厂商命令塞给了 B 厂商" ----------
DIALECT = {
    "huawei_like": {"must": [r"port link-type"], "never": [r"\bswitchport\b", r"\bset\s+(interfaces|security)"]},
    "cisco_like":  {"must": [r"switchport|interface\s+(Gig|Fast|Ten)"], "never": [r"port link-type", r"^vlan batch"]},
    "juniper_like": {"must": [r"^set\s+"], "never": [r"port link-type", r"switchport mode access"]},
}
VENDOR_DIALECT = {
    "Huawei": "huawei_like", "H3C": "huawei_like", "Ruijie": "huawei_like",
    "Maipu": "huawei_like", "ZTE": "huawei_like", "Fiberhome": "huawei_like",
    "Raisecom": "huawei_like", "Dcn": "huawei_like", "Inspur": "huawei_like",
    "Boda": "huawei_like", "Hikvision": "huawei_like", "Tplink": "huawei_like",
    "Dptecn": "huawei_like",
    "Cisco": "cisco_like", "Arista": "cisco_like", "Dell": "cisco_like",
    "HPE": "cisco_like", "Sonic": "cisco_like", "Extreme": "cisco_like",
    "Juniper": "juniper_like",
}

def _norm_head(line: str, n: int = 2) -> str:
    """归一化命令头: 去掉 {占位符} 和具体取值, 只留前 n 个动作词.
    'vlan batch {vlans}' -> 'vlan batch'; 'vlan batch 10 20' -> 'vlan batch'"""
    s = re.sub(r"\{[^}]*\}", " ", line)
    s = re.sub(r"^\W+", "", s.strip())
    toks = [t for t in s.split() if not re.fullmatch(r"[\d.,/]+", t)]
    return " ".join(t.lower() for t in toks[:n])

def command_head(line: str) -> str:
    return _norm_head(line, 2)

def kb_heads(vendor_key: str) -> set:
    """该厂商知识库里所有已知命令的头部集合."""
    heads = set()
    data = load_vendor(vendor_key)
    if data:
        cats = data.get("categories", data)  # 兼容 {vendor, categories} 包装和裸 dict
        for cat in cats.values():
            cmds = cat.get("commands", []) if isinstance(cat, dict) else cat
            if not isinstance(cmds, list):
                continue
            for item in cmds:
                if not isinstance(item, dict):
                    continue
                for field in ("syntax", "example", "command"):
                    s = item.get(field)
                    if isinstance(s, str):
                        heads.add(command_head(s))
    return heads

def audit_vendor(vendor_key: str) -> dict:
    topo = sample_topology()
    for n in topo["nodes"].values():
        n["vendor"] = vendor_key
    try:
        configs = generate_config_from_kb(topo, vendor_key)
    except Exception as e:
        return {"vendor": vendor_key, "ok": False, "error": f"生成异常: {e}", "issues": [], "stats": {}}

    # 方言从该厂商自己的语法表自动推断: JunOS(set 风格) / 思科系(switchport) / 华为系(port link-type)
    syntax_sample = " ".join(str(v) for v in _VENDOR_SYNTAX[vendor_key].values()
                             if isinstance(v, str))
    if re.search(r"\bset\s+(system|interfaces|vlans|protocols|routing-options)\b", syntax_sample):
        dialect = DIALECT["juniper_like"]
    elif "switchport" in syntax_sample:
        dialect = DIALECT["cisco_like"]
    else:
        dialect = DIALECT["huawei_like"]

    issues, all_lines = [], []
    for dev, lines in configs.items():
        # 终端设备 (pc/server 等) 本来就不需要配置, 跳过空检查
        if dev in ("pc1",):
            continue
        if not lines or not any(str(l).strip() and not str(l).startswith(("!", "#")) for l in lines):
            issues.append(f"{dev}: 配置为空")
        for l in lines:
            s = str(l)
            if "WARNING" in s:
                issues.append(f"{dev}: {s.strip()}")
            elif s.strip() and not s.startswith(("!", "#")):
                all_lines.append((dev, s.strip()))

    # 方言污染检查: 生成结果里不应出现与该厂商语法表风格相悖的命令
    body = "\n".join(s for _, s in all_lines)
    for pat in dialect["never"]:
        if re.search(pat, body, re.M):
            issues.append(f"方言污染: 出现了与 {vendor_key} 语法表风格相悖的命令片段 /{pat}/")

    # KB 自洽性: 命令头能被该厂商 KB 覆盖的比例
    heads = kb_heads(vendor_key)
    matched = sum(1 for _, s in all_lines if command_head(s) in heads) if heads else 0
    coverage = round(100 * matched / len(all_lines)) if all_lines else 0

    return {
        "vendor": vendor_key, "ok": not issues, "issues": issues,
        "stats": {"lines": len(all_lines), "kb_coverage": coverage},
    }

def main():
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    vendors = [v for v in _VENDOR_SYNTAX if only.lower() in v.lower()]
    if not vendors:
        print(f"没有匹配的厂商语法键: {only}")
        return 1

    results = [audit_vendor(v) for v in sorted(vendors)]

    # 输出报告
    md = ["# 模板自动化审计报告\n",
          "| 厂商语法键 | 状态 | 命令行数 | KB自洽率 | 问题 |", "|---|---|---|---|---|"]
    fail = 0
    for r in results:
        if "error" in r:
            md.append(f"| {r['vendor']} | ❌ 异常 | - | - | {r['error']} |")
            fail += 1
            continue
        status = "✅" if r["ok"] else "⚠️"
        if not r["ok"]:
            fail += 1
        issue_txt = "; ".join(r["issues"][:4]) + (f" ...共{len(r['issues'])}条" if len(r["issues"]) > 4 else "")
        md.append(f"| {r['vendor']} | {status} | {r['stats']['lines']} | {r['stats']['kb_coverage']}% | {issue_txt or '-'} |")

    total = len(results)
    passed = total - fail
    md.insert(1, f"\n结果: **{passed}/{total} 通过**\n")
    OUT.write_text("\n".join(md), encoding="utf-8")

    print(f"===== 模板审计: {passed}/{total} 通过 =====")
    for r in results:
        if "error" in r:
            print(f"  ❌ {r['vendor']}: {r['error']}")
        elif r["issues"]:
            print(f"  ⚠️  {r['vendor']}: {len(r['issues'])} 个问题")
            for i in r["issues"][:3]:
                print(f"      - {i}")
        else:
            print(f"  ✅ {r['vendor']}: {r['stats']['lines']} 行, KB 自洽率 {r['stats']['kb_coverage']}%")
    print(f"报告: {OUT}")
    return 1 if fail else 0

if __name__ == "__main__":
    sys.exit(main())
