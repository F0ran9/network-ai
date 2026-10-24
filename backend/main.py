import os
import json
from dotenv import load_dotenv
load_dotenv()  # 必须在导入 openai 之前加载 .env

import asyncio
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn

from config_generator import generate_config
import llm_client
from prompts import CHAT_SYSTEM_PROMPT, VENDOR_STYLES
from kb_engine import (
    search as kb_search, list_vendors, get_vendor_categories, get_category_commands,
    generate_config_from_kb as kb_generate, validate_cli_command,
)
from vision_analyzer import analyze_topology_image
from device_connector import push_config, run_ping_tests, collect_state
import network_scanner

app = FastAPI(title="Network Config Generator")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 平台鉴权: 单密码登录 -> 内存会话 token (7 天有效)
# ============================================================
import time
import secrets
from fastapi import Header

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
SESSION_TTL = 7 * 24 * 3600
_sessions: dict = {}  # token -> 过期时间戳


def _ensure_password() -> str:
    """APP_PASSWORD 未配置时随机生成一个并写入 .env (首次启动自动初始化)."""
    pw = os.getenv("APP_PASSWORD", "").strip()
    if pw:
        return pw
    pw = secrets.token_urlsafe(9)  # 12 位含大小写数字, 无特殊符号便于手输
    try:
        with open(ENV_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n# 平台登录密码 (自动生成, 可修改)\nAPP_PASSWORD={pw}\n")
    except OSError:
        pass
    os.environ["APP_PASSWORD"] = pw
    print(f"\n{'=' * 62}\n  首次启动已生成随机登录密码: {pw}\n  已保存到 {ENV_FILE}\n  登录平台后可在【设置 → 全局参数设置 → 平台登录密码】中修改\n{'=' * 62}\n", flush=True)
    return pw


def _update_env_file(key: str, value: str):
    """把 KEY=VALUE 写回 .env: 存在则替换, 不存在则追加."""
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            replaced = True
            break
    if not replaced:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"{key}={value}\n")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.environ[key] = value


class LoginRequest(BaseModel):
    password: str


@app.post("/api/auth/login")
async def api_auth_login(request: LoginRequest):
    if not secrets.compare_digest(request.password or "", _ensure_password()):
        raise HTTPException(status_code=401, detail="密码错误")
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_TTL
    return {"token": token, "expires_in": SESSION_TTL}


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@app.post("/api/auth/change-password")
async def api_auth_change_password(request: ChangePasswordRequest):
    """修改平台登录密码: 校验原密码后写回 .env, 已登录会话保持有效."""
    if not secrets.compare_digest(request.old_password or "", _ensure_password()):
        raise HTTPException(status_code=401, detail="原密码错误")
    new_pw = (request.new_password or "").strip()
    if len(new_pw) < 8:
        raise HTTPException(status_code=400, detail="新密码至少 8 位")
    if len(new_pw) > 128:
        raise HTTPException(status_code=400, detail="新密码过长")
    _update_env_file("APP_PASSWORD", new_pw)
    return {"ok": True, "message": "密码已更新, 下次登录使用新密码"}


@app.middleware("http")
async def auth_middleware(request, call_next):
    path = request.url.path
    # 登录接口与前端静态资源放行, 其余 /api/* 一律要求会话 token
    if path.startswith("/api/") and path != "/api/auth/login":
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        exp = _sessions.get(token)
        if not exp or exp < time.time():
            _sessions.pop(token, None)
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=401, content={"detail": "未登录或会话已过期"})
    return await call_next(request)


# ============================================================
# AI 配置 (前端可视化设置, 保存即生效无需重启)
# ============================================================
SECRET_KEYS = ("AI_API_KEY", "DEEPSEEK_API_KEY")


def _mask(v: str) -> str:
    if not v:
        return ""
    return v[:4] + "****" + v[-4:] if len(v) > 10 else "****"


@app.get("/api/settings")
async def api_settings_get():
    import llm_client
    cfg = llm_client.get_provider_config()
    name = (os.getenv("AI_NAME", "") or "").strip()
    if not name:
        # 根据当前配置给个默认显示名
        b = cfg["base_url"] or ""
        if "deepseek" in b:
            name = "deepseek"
        elif "bigmodel" in b or "glm" in b:
            name = "glm"
        elif "siliconflow" in b:
            name = "siliconflow"
        else:
            name = cfg["model"].split("/")[0] if cfg["model"] else "custom"
    return {
        "provider": {
            "name": name,
            "format": cfg["format"],
            "api_key_set": bool(cfg["api_key"]),
            "api_key_masked": _mask(cfg["api_key"]),
            "base_url": cfg["base_url"],
            "model": cfg["model"],
        },
        # 兼容旧前端字段
        "deepseek": {
            "api_key_set": bool(cfg["api_key"]),
            "api_key_masked": _mask(cfg["api_key"]),
            "base_url": cfg["base_url"],
            "model": cfg["model"],
        },
    }


class SettingsRequest(BaseModel):
    name: str = ""               # 配置显示名 (如 deepseek / glm)
    format: str = ""             # openai | anthropic
    api_key: str = ""            # 空串 = 保持不变
    base_url: str = ""
    model: str = ""
    # 兼容旧字段
    deepseek_api_key: str = ""
    deepseek_base_url: str = ""
    deepseek_model: str = ""


@app.post("/api/settings")
async def api_settings_post(request: SettingsRequest):
    api_key = request.api_key.strip() or request.deepseek_api_key.strip()
    base_url = request.base_url.strip() or request.deepseek_base_url.strip()
    model = request.model.strip() or request.deepseek_model.strip()
    fmt = (request.format or "").strip().lower()
    name = request.name.strip()

    if name:
        _update_env_file("AI_NAME", name)
    if fmt in ("openai", "anthropic"):
        _update_env_file("AI_FORMAT", fmt)
    if api_key:
        _update_env_file("AI_API_KEY", api_key)
    if base_url:
        _update_env_file("AI_BASE_URL", base_url)
    if model:
        _update_env_file("AI_MODEL", model)
    # 客户端缓存失效, 下次调用用新配置重建
    import llm_client
    llm_client.reset_client()
    import config_generator
    config_generator.reset_client()
    return {"status": "success"}


@app.post("/api/settings/test")
async def api_settings_test():
    """用一次最小对话请求验证当前 AI 配置连通性."""
    import llm_client
    cfg = llm_client.get_provider_config()
    if not cfg["api_key"]:
        return {"ok": False, "error": "API Key 未配置"}
    try:
        text = llm_client.chat_completion(
            messages=[{"role": "user", "content": "ping"}], max_tokens=1,
        )
        return {"ok": True, "model": cfg["model"], "format": cfg["format"]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/settings/models")
async def api_settings_models():
    """从服务商接口自动获取可用模型列表."""
    import llm_client
    try:
        models = llm_client.list_models()
        return {"ok": True, "models": models}
    except Exception as e:
        return {"ok": False, "models": [], "error": str(e)[:300]}

# ---- Models ----
class TopologyRequest(BaseModel):
    topology: dict
    vendor: str = "Huawei"
    globalSettings: dict = None

class ChatRequest(BaseModel):
    messages: list
    topology: dict
    vendor: str = "Huawei"
    configs: dict = {}

# ---- Routes ----
@app.post("/api/generate")
async def api_generate(request: TopologyRequest):
    try:
        config = generate_config(request.topology, request.vendor, global_settings=request.globalSettings)
        return {"status": "success", "config": config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/generate/kb")
async def api_generate_kb(request: TopologyRequest):
    """KB-only config generation (works offline, no AI call)."""
    try:
        config = kb_generate(request.topology, request.vendor, request.globalSettings)
        return {"status": "success", "config": config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat/stream")
async def api_chat_stream(request: ChatRequest):
    vendor = request.vendor.capitalize()
    style = VENDOR_STYLES.get(vendor, VENDOR_STYLES["default"])
    topo_str = json.dumps(request.topology, ensure_ascii=False, indent=2)
    configs_str = json.dumps(request.configs, ensure_ascii=False, indent=2) if request.configs else "尚未生成配置"
    system_prompt = CHAT_SYSTEM_PROMPT.format(
        topology_context=topo_str, vendor=vendor, style=style, configs_context=configs_str,
    )

    api_messages = [{"role": "system", "content": system_prompt}] + request.messages

    async def generate():
        for token in llm_client.stream_chat(api_messages, temperature=0.3, max_tokens=2048):
            if token:
                yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ---- Topology Image Analysis (DeepSeek 原生视觉) ----
@app.post("/api/analyze/topology-image")
async def api_analyze_topology_image(
    file: UploadFile = File(...),
    vendor: str = Form("Huawei"),
    generate_configs: bool = Form(True),
):
    """Upload a network topology diagram image for AI analysis.

    Accepts: jpg, jpeg, png, bmp, webp
    Uses DeepSeek native vision (same API key as config generation).
    Returns: extracted topology, analysis report, and optionally auto-generated configs.
    """
    allowed = {"image/jpeg", "image/png", "image/bmp", "image/webp", "image/gif"}
    if file.content_type and file.content_type not in allowed:
        raise HTTPException(400, f"不支持的文件类型: {file.content_type}，仅支持 JPG/PNG/BMP/WebP")

    image_bytes = await file.read()
    if len(image_bytes) == 0:
        raise HTTPException(400, "上传的文件为空")
    if len(image_bytes) > 20 * 1024 * 1024:
        raise HTTPException(400, "图片大小不能超过 20MB")

    try:
        # 视觉分析耗时较长, 放线程池避免阻塞事件循环
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: analyze_topology_image(image_bytes, file.filename or "topology.png", vendor)
        )
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        raise HTTPException(500, detail=f"视觉分析失败: {str(e)}")

    response = {
        "status": "success",
        "extracted_topology": result["extracted_topology"],
        "analysis_report": result["analysis_report"],
        "warnings": result.get("warnings", []),
    }

    if generate_configs and result["extracted_topology"].get("nodes"):
        try:
            configs = generate_config(result["extracted_topology"], vendor, use_ai_fallback=False)
            response["configs"] = configs
        except Exception as e:
            response["configs"] = {}
            response["config_error"] = str(e)

    return response

# ---- Knowledge Base API ----
@app.get("/api/kb/search")
async def api_kb_search(q: str = "", vendor: str = "all", category: str = "all"):
    return kb_search(q, vendor, category)

@app.get("/api/kb/vendors")
async def api_kb_vendors():
    return {"vendors": list_vendors()}

@app.get("/api/kb/categories")
async def api_kb_categories(vendor: str = "Huawei"):
    return get_vendor_categories(vendor)

@app.get("/api/kb/commands")
async def api_kb_commands(vendor: str = "Huawei", category: str = "vlan"):
    return get_category_commands(vendor, category)

# ---- CLI Validation ----
class CliValidateRequest(BaseModel):
    command: str
    vendor: str = "Huawei"
    mode: str = "user"  # user, system, interface, vlan, ospf
    device_context: dict = {}

@app.post("/api/cli/validate")
async def api_cli_validate(request: CliValidateRequest):
    """Validate a CLI command against the knowledge base."""
    try:
        result = validate_cli_command(request.command, request.vendor, request.mode)
        return result
    except Exception as e:
        # 校验器出错时不能假装命令有效 — 明确返回"无法校验"
        return {"valid": False, "response": "", "suggested_fix": None,
                "help_text": f"校验器内部错误, 本次无法校验该命令: {e}"}

# ---- Device Connection (真机下发/验收) ----
class DevicePushRequest(BaseModel):
    host: str
    deviceType: str            # huawei / hp_comware / cisco_ios / ruijie_os
    username: str
    password: str
    commands: list             # 配置命令列表 (注释行会被自动过滤)
    dryRun: bool = True        # 默认只预览!
    backup: bool = True
    port: int = 22

class PingTestRequest(BaseModel):
    host: str
    deviceType: str
    username: str
    password: str
    source: str                # 源地址 (VLANIF IP), 验证业务网段真实可达
    targets: list              # [{name, ip}, ...]
    count: int = 5
    port: int = 22

class DeviceStateRequest(BaseModel):
    host: str
    deviceType: str
    username: str
    password: str
    port: int = 22

def _run_blocking(fn, **kwargs):
    """netmiko 是阻塞 IO, 扔线程池避免卡死事件循环."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(fn, **kwargs).result(timeout=180)

@app.post("/api/device/push")
async def api_device_push(request: DevicePushRequest):
    """真机下发配置. 默认 dryRun=true 只连接+备份+预览; dryRun=false 才真实下发."""
    try:
        result = await _run_blocking(
            push_config, host=request.host, device_type=request.deviceType,
            username=request.username, password=request.password,
            commands=request.commands, dry_run=request.dryRun,
            backup=request.backup, port=request.port,
        )
        return {"status": "success", "data": result}
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        raise HTTPException(500, detail=f"设备连接/下发失败: {e}")

@app.post("/api/device/ping-tests")
async def api_device_ping_tests(request: PingTestRequest):
    """连通性验收: 从设备源地址 ping 目标矩阵, 全部通过才算'真的通'."""
    try:
        result = await _run_blocking(
            run_ping_tests, host=request.host, device_type=request.deviceType,
            username=request.username, password=request.password,
            source=request.source, targets=request.targets,
            count=request.count, port=request.port,
        )
        return {"status": "success", "data": result}
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        raise HTTPException(500, detail=f"设备连接/测试失败: {e}")

@app.post("/api/device/state")
async def api_device_state(request: DeviceStateRequest):
    """抓取设备接口/VLAN/邻居状态 (排障用), 同时存档到 device_backups/."""
    try:
        result = await _run_blocking(
            collect_state, host=request.host, device_type=request.deviceType,
            username=request.username, password=request.password, port=request.port,
        )
        return {"status": "success", "data": result}
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        raise HTTPException(500, detail=f"设备连接失败: {e}")


# ============================================================
# 网络自动发现: SSH+LLDP/CDP 递归扫描 -> 拓扑 + 诊断报告
# ============================================================
class DiscoverRequest(BaseModel):
    seedIp: str
    username: str
    password: str
    vendor: str = "huawei"      # huawei | h3c | cisco | ruijie
    sshPort: int = 22
    maxDepth: int = 3
    demo: bool = False          # 演示模式: 返回固定示例数据


@app.post("/api/discover/stream")
async def api_discover_stream(request: DiscoverRequest):
    """SSE 流式网络发现: 逐台设备推送进度, 结束推送完整拓扑+诊断."""
    if not request.demo and not request.seedIp.strip():
        raise HTTPException(400, detail="请填写种子设备 IP")

    async def gen():
        import queue as _q
        q: _q.Queue = _q.Queue()

        def progress(msg: str):
            q.put(msg)

        def work():
            try:
                if request.demo:
                    data = network_scanner.demo_scan(progress)
                else:
                    data = network_scanner.discover_network(
                        request.seedIp.strip(), request.username, request.password,
                        vendor=request.vendor, max_depth=request.maxDepth,
                        ssh_port=request.sshPort, progress=progress)
                q.put(("result", data))
            except Exception as e:
                q.put(("error", str(e)))

        import threading
        threading.Thread(target=work, daemon=True).start()

        import json as _json
        while True:
            item = await asyncio.get_event_loop().run_in_executor(None, q.get)
            if isinstance(item, tuple):
                kind, payload = item
                yield f"data: {_json.dumps({'type': kind, 'data': payload}, ensure_ascii=False)}\n\n"
                if kind in ("result", "error"):
                    break
            else:
                yield f"data: {_json.dumps({'type': 'progress', 'message': item}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# 开发模式：如果存在前端构建，直接服务静态文件
if os.path.exists("../frontend/dist"):
    app.mount("/", StaticFiles(directory="../frontend/dist", html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=5732, reload=False)
