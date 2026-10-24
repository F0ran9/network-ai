"""Vision-based topology diagram analyzer.

统一走 llm_client (多厂商协议: OpenAI 兼容 / Anthropic 兼容),
与配置生成 / AI 助手共用同一组 AI 配置 (前端"AI 设置"管理)。

配置项 (backend/.env, 前端可视化配置):
  AI_FORMAT   openai | anthropic
  AI_API_KEY  与配置生成共用同一把 key
  AI_BASE_URL 可选
  AI_MODEL    可选 (识图与生成共用一个模型)
"""
import base64
import io
import json
import os
import re
from typing import Dict, Any, Tuple

from dotenv import load_dotenv
load_dotenv()


def _vision_model() -> str:
    """识图模型名: 默认 deepseek-chat, 可用 DEEPSEEK_VISION_MODEL 覆盖."""
    return os.getenv("DEEPSEEK_VISION_MODEL", "deepseek-chat")


_IMAGE_DESCRIBE_PROMPT = """请详细描述这张网络拓扑图。

列出图中所有信息：
1. 每个设备的名称/标注文字、设备类型（路由器/交换机/防火墙/PC/服务器/AP/AC等）、品牌型号（如能看到）
2. 设备之间的连线关系，谁连到谁
3. 端口标注、VLAN ID、IP 地址、网段等文字信息
4. 安全区域的划分（如 DMZ、内网、外网等标注）
5. 任何其他可见的文字、符号、图例

请用中文详细输出，不要遗漏任何细节。"""

_ANALYSIS_SYSTEM_PROMPT = """你是一位资深网络架构师。你的任务是把拓扑图**原样**转成结构化 JSON。你是一台"提取器"，不是"设计师"。

## 最高铁律：忠实原图（违反任何一条即任务失败）

1. **设备数量一比一**：原图画一台防火墙就是一台，画两台就是两台。绝对禁止凭"高可用经验""常见架构"补画、合并或删除任何设备。原图没有的设备一个都不能造出来。
2. **禁止编造主备**：除非原图明确写了"主/备/HA/双机"，否则 label 里禁止出现"（主）（备）"字样，禁止填 redundancy 字段。看不出来就是看不出来。
3. **禁止发明安全域/架构层**：原图没有 DMZ 域、没有"出口安全区"等划分，就绝不能造。原图用虚线框/色块分了几个组，就提取几个组，组名照抄原图。
4. **连线严格照抄**：谁连谁、从哪连到哪，与原图完全一致。禁止按"最佳实践"重排链路（例如不要把专线流量改道经过防火墙、不要把串接设备挪到别的位置）。
5. **不确定就留空**：端口、IP、VLAN、带宽、链路属性，原图没标注就留空字符串，禁止编造 "GE0/0/1" 之类的默认值。
6. 自查：逐个数原图里的设备图标和连线，数量必须与 JSON 中 nodes/links 一致。特别注意体积小、放在交换机下方的服务器类设备（**Portal 认证服务器、虚拟化服务器、DHCP/DNS 服务器等**）也是设备，必须提取；它们上联谁就连谁，不要挪位。

## 图标与设备的对应判定（先判定，再提取）

- **一组图标共用一个设备名 + 一个 IP = 一台设备**：紧挨着的两个相同图标若共用同一个设备名和同一个 IP（典型的 HA 双机画法），只提取为一台设备，禁止拆成两台节点；可在 description 注明"原图画双图标"。
- **同组图标各自有独立连线时拆开**：若组内两个图标各自连不同的对象、语义独立（例如 SDWAN 组内一台接 MPLS 专线、一台接互联网侧隧道），则提取为两台设备，label 加后缀区分（如"SDWAN路由器-专线""SDWAN路由器-隧道"）。
- **只有文字、没有图标的标注不是设备**："SDWAN""MPLSVPN"这类线旁/框旁文字是链路标注或分组名：链路文字写进对应 link 的 linkLabel，分组名写进 zones，**禁止**建成节点。
- **云朵图标只代表它标注的那条线路**：一个云朵图标 + 旁边的文字标注 = 一条运营商线路，不要把文字标注再额外建成第二个云节点。例如图中已有"电信200M"云和"联通100M"云，另一处文字"电信电路接入"若紧挨某条线，它是那条 MPLS 专线线路的标注——该专线应表现为一条连到 SDWAN 路由器的链路（linkLabel="电信电路接入 MPLS专线"），而不是新建一个云设备。识别出的云节点数必须等于原图云朵图标数。

## 连线自查（最易错，逐台核对）

- 数清楚原图中**每台设备引出几条线、分别连到谁**，输出的 links 中该设备的连线数和对象必须一致，禁止增删改。
- **一台设备只连它在原图中的邻居**：先逐台列出每个防火墙在原图中的邻居设备（上联谁、下联谁），再输出。典型错误是视觉上离得远的两台设备被强行连起来：**一台设备同时出现在两条不同链路里几乎总是错的**。例如：出口链路（互联网云→负载均衡→外网防火墙→上网行为管理→核心）里的防火墙只有外网防火墙一台；内网防火墙如果原图只连"服务器汇聚交换机"和"商业核心交换机"，它就必须恰好只有这两条连线，与出口链路完全无关。
- **防火墙位置照抄**：内网/服务器区边界防火墙串在谁和谁之间就输出谁，绝不能因为它名字带"防火墙"就把它挪到互联网出口链路上；出口链路上的设备依次也照抄，不要插入原图没有的设备。互联网出口链路里只应有**一台**防火墙（外网防火墙）；**其余防火墙都是服务器区/内网边界防火墙，它们的下联是服务器区的汇聚交换机**（不是消控/监控核心交换机）。
- **专线云连专线设备**：MPLS/专线类的云朵（标注如"电信电路接入"）上联应连到**专线接入路由器（SDWAN 路由器）**，而不是核心交换机；专线流量走"云 → SDWAN 路由器 → 商业核心"这条独立路径，不经过外网防火墙、不上网行为管理。
- **双核心横向对等**：两台核心交换机（如商业核心与消控/监控核心）之间是横向互联，互不上下级；其他设备上联哪台就连哪台（按原图连线），不要把所有上联流量画成先经过同一台核心。
- **服务器归属看连线**：服务器/终端连接原图中它的连线指向的那台交换机（通常是正上方或同分组框内的），不要默认全挂到最底层或错接到别的交换机。

## 命名规范
- label 照抄原图设备名，可补充业务前缀使含义更清晰（如"办公AC""商业AC"），但不得添加原图没有的架构含义。

## 字段填写规范
- **mgmtIp 逐台核对**：原图大多数设备旁都直接标注了 IP（如 "10.94.89.246"），一台一台提取到 mgmtIp 字段，一台都不能漏；图上确实没标 IP 的才留空。
- linkLabel 只写原图标注的链路文字（如"电信200M互联网链路""SDWAN隧道"），原图没写就留空；**禁止**写"XX至XX"这类重复两端设备名的文字
- mode：原图能明确判断是 Trunk（VLAN 透传/Eth-Trunk 捆绑）还是三层互联时才填 trunk|l3|access，判断不了填 unknown
- bandwidth：原图标注了带宽（如 200M、10GE）才填，否则留空

## category 取值
router=路由器, switch=交换机, firewall=防火墙, lb=负载均衡, sdwan=SDWAN/专线路由器, behavior=上网行为管理/流控设备, terminal=PC/打印机, server=服务器, wireless=AP/AC, other=其他
（负载均衡填 lb、上网行为管理填 behavior、SDWAN 路由器填 sdwan，不要笼统填 router/other）

## 输出格式（严格遵守JSON，不要包含其他文字）

{
  "extracted_topology": {
    "nodes": {
      "<device_key>": {
        "label": "设备名称（照抄原图，可加业务前缀）",
        "category": "router|switch|firewall|lb|sdwan|behavior|terminal|server|wireless|other",
        "role": "router|core|access|security|endpoint|wireless",
        "vendor": "Huawei|Cisco|H3C|Ruijie|unknown",
        "zone": "原图分组框名称（照抄），无分组框留空",
        "model": "设备型号（识别不出填unknown）",
        "mgmtIp": "设备旁标注的管理IP，没有则留空",
        "description": "设备功能描述（依据原图标注，不脑补）"
      }
    },
    "links": [
      {
        "from": "源设备key",
        "to": "目标设备key",
        "fromPort": "原图标注的源端口，无标注留空",
        "toPort": "原图标注的目标端口，无标注留空",
        "mode": "trunk|access|l3|unknown",
        "redundancy": "primary|backup（原图明确为主备链路才填，否则省略）",
        "linkLabel": "原图标注的链路文字，无标注留空",
        "bandwidth": "原图标注的带宽，无标注留空"
      }
    ],
    "zones": [
      { "name": "原图分组框/业务框名称（照抄）", "members": ["该框内设备key", "..."] }
    ]
  },
  "analysis_report": {
    "topology_overview": "拓扑总览：设备数量、连接关系。只描述原图事实，不做架构评价。",
    "security_architecture": "原图中的隔离手段（防火墙/ACL等），原图没有明确的安全设计就如实说明。",
    "redundancy_ha": "原图可见的冗余情况；看不出来就明确写'原图未标注，无法判断'，禁止推测。",
    "traffic_flow": "按原图连线描述流量走向（外网→出口→核心→各业务区）。",
    "config_recommendations": "配置建议：VLAN/STP/路由/ACL/管理IP规划（这部分是你的专业建议，与原图事实分开）。",
    "risk_notes": "风险提示：原图本身的薄弱点（如缺少冗余、无安全域划分），如实指出。"
  }
}

## 其他要求
1. 设备key用有意义的英文（core_sw_1, fw_outside_1, ac_office_1）
2. zones 数组：原图有虚线分组框/色块分区才填，成员是该框内的设备 key；原图没有就填空数组 []
3. 分析报告用通俗中文，每项2-4句话
4. 模糊信息留空或标注unknown，禁止按经验补全

请直接输出JSON，不要包含其他任何文字。"""


def _get_deepseek_client():
    """兼容入口: 统一走 llm_client (多厂商协议)."""
    import llm_client
    cfg = llm_client.get_provider_config()
    if not cfg["api_key"]:
        raise ValueError("API Key 未配置，请在后端 .env 或前端\"AI 设置\"中配置")
    return llm_client


def _resize_if_needed(image_bytes: bytes, max_size_mb: float = 5.0) -> bytes:
    """Resize image proportionally if it exceeds max_size_mb."""
    max_bytes = int(max_size_mb * 1024 * 1024)
    if len(image_bytes) <= max_bytes:
        return image_bytes

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        ratio = (max_bytes / len(image_bytes)) ** 0.5
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        img_format = img.format or "JPEG"
        img.save(buf, format=img_format, optimize=True)
        return buf.getvalue()
    except Exception:
        return image_bytes


def _get_mime_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".bmp": "image/bmp",
        ".webp": "image/webp", ".gif": "image/gif",
    }.get(ext, "image/png")


def _parse_vision_response(raw_text: str) -> Dict[str, Any]:
    """Multi-strategy JSON parser for vision model responses."""
    text = raw_text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    try:
        fixed = re.sub(r',\s*}', '}', text)
        fixed = re.sub(r',\s*]', ']', fixed)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    raise ValueError(f"无法解析视觉模型返回的JSON。原始响应前500字符: {text[:500]}")


def _validate_topology(extracted: dict) -> Tuple[bool, list]:
    """Validate extracted topology. Returns (is_valid, warnings)."""
    warnings = []
    nodes = extracted.get("nodes", {})
    links = extracted.get("links", [])

    if not nodes:
        return False, ["拓扑中没有识别到任何设备"]

    valid_categories = {"router", "switch", "firewall", "lb", "sdwan", "behavior",
                        "terminal", "server", "wireless", "other"}
    valid_roles = {"router", "core", "access", "security", "endpoint", "wireless"}
    for key, node in nodes.items():
        cat = node.get("category", "")
        if cat not in valid_categories:
            warnings.append(f"设备 '{key}' 的类型 '{cat}' 不在标准类型中，已标记为 'other'")
            node["category"] = "other"
        role = node.get("role", "")
        if role not in valid_roles:
            node["role"] = "endpoint"
        # 忠实原图: AI 未填 mgmtIp/model 时保持空, 不编造

    node_keys = set(nodes.keys())
    for i, link in enumerate(links):
        frm = link.get("from", "")
        to = link.get("to", "")
        if frm and frm not in node_keys:
            warnings.append(f"链路 #{i}: 源设备 '{frm}' 在节点列表中不存在")
        if to and to not in node_keys:
            warnings.append(f"链路 #{i}: 目标设备 '{to}' 在节点列表中不存在")
        if not link.get("mode"):
            link["mode"] = "unknown"  # 原图未标注链路属性时不编造
        if not link.get("fromPort"):
            link["fromPort"] = ""  # 原图未标注端口时留空, 禁止编造 GE0/0/1
        if not link.get("toPort"):
            link["toPort"] = ""

    return len(warnings) < 5, warnings


def _analyze_image_with_deepseek(image_b64: str, mime_type: str, preferred_vendor: str) -> str:
    """视觉单步分析: 图片直接进模型, 一步产出结构化 JSON (协议自适应)."""
    import llm_client

    # 关键: 只要求输出 JSON。若允许模型"先描述再输出", 描述会耗尽 token 导致 JSON 缺失
    user_text = (
        "请识别这张网络拓扑图，直接输出分析JSON。\n"
        f"假设图中设备厂商为 {preferred_vendor}（如无法识别则标注unknown）。\n\n"
        "要求：\n"
        "1. 只输出一个 JSON 对象，不要输出任何描述性文字、标题或 markdown 代码块\n"
        "2. JSON 必须包含 extracted_topology（nodes+links）和 analysis_report 两个顶级字段，结构如下\n"
        "3. 短横线标注的 IP、设备名、端口等信息要如实记录到对应字段\n"
        "4. analysis_report 各字段用通俗中文，每项 2-4 句话即可，不要长篇大论\n\n"
        + _ANALYSIS_SYSTEM_PROMPT
    )

    return llm_client.vision_completion(user_text, image_b64, mime_type,
                                        temperature=0.2, max_tokens=8192)


def _postprocess_fix_links(topo: dict) -> list:
    """现场铁律的确定性链路校正（不依赖 AI，每次识别后强制执行）。

    铁律1: 内网防火墙只串在【服务器汇聚 ↔ 商业核心】之间, 不在出口主链路上。
    铁律2: 电信电路/MPLS 专线云连到 SDWAN 专线路由器, 不直连核心交换机。
    返回校正说明列表 (并入 warnings, 让用户知道图被自动修正过)。
    """
    fixes = []
    nodes = topo.get("nodes", {})
    links = topo.get("links", [])
    if not nodes or not links:
        return fixes

    # 清理 AI 偶发自环 (原图并排双图标被当成两台又连线的场景)
    before = len(links)
    links[:] = [l for l in links if l.get("from") != l.get("to")]
    if len(links) != before:
        fixes.append("已清理识别产生的自环连线")

    def find_node(*kws):
        # 先按 label 匹配 (避免 description 里提到别的设备导致误匹配),
        # 再退化为 label+description 联合匹配
        for k, n in nodes.items():
            label = n.get("label") or ""
            if any(kw in label for kw in kws):
                return k
        for k, n in nodes.items():
            text = f"{n.get('label') or ''} {n.get('description') or ''}"
            if any(kw in text for kw in kws):
                return k
        return None

    def link_between(a, b):
        for l in links:
            if {l.get("from"), l.get("to")} == {a, b}:
                return l
        return None

    # ---- 铁律1: 内网防火墙 = 服务器汇聚 ↔ 商业核心 ----
    fw_in = find_node("内网防火墙")
    agg_sw = find_node("服务器汇聚")
    core_biz = find_node("商业核心")
    if fw_in and agg_sw and core_biz:
        has_core = link_between(fw_in, core_biz) is not None
        # 删除内网防火墙上除商业核心外的所有连线 (摘出出口主链路)
        removed = [l for l in links
                   if fw_in in (l.get("from"), l.get("to"))
                   and {l.get("from"), l.get("to")} != {fw_in, core_biz}]
        if removed:
            links[:] = [l for l in links if l not in removed]
        if not has_core:
            links.append({"from": fw_in, "to": core_biz, "fromPort": "", "toPort": "",
                          "mode": "unknown", "linkLabel": "", "bandwidth": ""})
        if not link_between(fw_in, agg_sw):
            links.append({"from": agg_sw, "to": fw_in, "fromPort": "", "toPort": "",
                          "mode": "unknown", "linkLabel": "服务器区边界", "bandwidth": ""})
        if removed or not has_core:
            fixes.append("已按现场铁律校正：内网防火墙只串接在【服务器汇聚 ↔ 商业核心】之间，不在互联网出口主链路上")

    # ---- 铁律2: 专线云 → SDWAN 路由器 (不直连核心) ----
    wan_cloud = find_node("电信电路", "MPLS专线", "专线接入")
    sdwan_node = find_node("SDWAN路由器-专线") or find_node("SDWAN路由器") or find_node("SDWAN")
    if wan_cloud and sdwan_node and wan_cloud != sdwan_node:
        changed = False
        for l in links:
            if l.get("from") == wan_cloud and l.get("to") != sdwan_node:
                l["to"] = sdwan_node
                changed = True
            elif l.get("to") == wan_cloud and l.get("from") != sdwan_node:
                l["from"] = sdwan_node
                changed = True
        if changed:
            fixes.append("已按现场铁律校正：电信电路/MPLS 专线云对接 SDWAN 专线路由器，专线流量不直连核心交换机")

    return fixes


def analyze_topology_image(
    image_bytes: bytes,
    filename: str = "topology.png",
    preferred_vendor: str = "Huawei"
) -> Dict[str, Any]:
    """Analyze a network topology diagram image using DeepSeek native vision.

    Args:
        image_bytes: Raw image file bytes
        filename: Original filename (for MIME type detection)
        preferred_vendor: Preferred equipment vendor for config generation

    Returns:
        {
            "extracted_topology": {"nodes": {...}, "links": [...]},
            "analysis_report": {...},
            "warnings": [...]
        }
    """
    image_bytes = _resize_if_needed(image_bytes, max_size_mb=2.0)
    mime_type = _get_mime_type(filename)
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    raw_text = _analyze_image_with_deepseek(image_b64, mime_type, preferred_vendor)

    result = _parse_vision_response(raw_text)

    topo = result.get("extracted_topology", {})
    is_valid, warnings = _validate_topology(topo)
    if not is_valid and not topo.get("nodes"):
        raise ValueError(f"拓扑图分析失败：{'; '.join(warnings)}")

    # 现场铁律的确定性链路校正 (见函数注释)
    fixes = _postprocess_fix_links(topo)
    warnings = warnings + fixes

    return {
        "extracted_topology": topo,
        "analysis_report": result.get("analysis_report", {}),
        "warnings": warnings,
        "raw_response": raw_text,
    }
