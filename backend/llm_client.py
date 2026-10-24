"""统一的 LLM 客户端 —— 多厂商协议感知.

支持两种协议格式 (前端"AI 设置"里可选):
  openai    : OpenAI 兼容协议 (DeepSeek / GLM / SiliconFlow / Moonshot / OpenAI / 中转站...)
  anthropic : Anthropic 兼容协议 (Claude 官方 / GLM anthropic 端点 等)

配置读取优先级 (均在 backend/.env, 可由前端"AI 设置"写入):
  AI_FORMAT / AI_API_KEY / AI_BASE_URL / AI_MODEL
  为空时回退旧的 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL (向后兼容)
"""
import os
import json
from dotenv import load_dotenv

load_dotenv()

_client_cache = {"key": None, "client": None}

DEFAULTS = {
    "openai": {"base_url": "https://api.deepseek.com", "model": "deepseek-chat"},
    "anthropic": {"base_url": "https://api.anthropic.com", "model": "claude-sonnet-4-20250514"},
}


def get_provider_config() -> dict:
    """读取当前生效的 provider 配置 (含旧变量回退)."""
    fmt = (os.getenv("AI_FORMAT", "") or "").strip().lower()
    if fmt not in DEFAULTS:
        fmt = "openai"
    key = (os.getenv("AI_API_KEY", "") or "").strip() or os.getenv("DEEPSEEK_API_KEY", "").strip()
    base = (os.getenv("AI_BASE_URL", "") or "").strip() or os.getenv("DEEPSEEK_BASE_URL", "").strip()
    model = (os.getenv("AI_MODEL", "") or "").strip() or os.getenv("DEEPSEEK_MODEL", "").strip()
    if not base:
        base = DEFAULTS[fmt]["base_url"]
    if not model:
        model = DEFAULTS[fmt]["model"]
    return {"format": fmt, "api_key": key, "base_url": base, "model": model}


def _get_client():
    """按当前配置构建 (并缓存) SDK 客户端; 配置变化时自动重建."""
    cfg = get_provider_config()
    cache_key = (cfg["format"], cfg["api_key"], cfg["base_url"])
    if _client_cache["client"] is None or _client_cache["key"] != cache_key:
        if cfg["format"] == "anthropic":
            from anthropic import Anthropic
            _client_cache["client"] = Anthropic(api_key=cfg["api_key"], base_url=cfg["base_url"] or None)
        else:
            from openai import OpenAI
            _client_cache["client"] = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
        _client_cache["key"] = cache_key
    return _client_cache["client"]


def reset_client():
    """配置更新后使缓存客户端失效."""
    _client_cache["client"] = None
    _client_cache["key"] = None


def _split_system(messages: list):
    """把 messages 里的 system 拆出来 (anthropic 需要 system 独立传参)."""
    system = ""
    rest = []
    for m in messages:
        if m.get("role") == "system" and not system:
            system = m.get("content", "")
        else:
            rest.append(m)
    return system, rest


def _text_from_anthropic_content(content) -> str:
    """从 anthropic 响应 content 块列表中提取文本 (跳过 thinking 等非文本块)."""
    for block in content or []:
        if getattr(block, "type", "") == "text" or hasattr(block, "text"):
            t = getattr(block, "text", None)
            if t:
                return t.strip()
    return ""


def chat_completion(messages: list, temperature: float = 0.2, max_tokens: int = 4096,
                    force_json: bool = False) -> str:
    """一次对话补全, 返回文本内容. force_json 仅在 openai 协议生效 (不支持时自动重试去掉)."""
    cfg = get_provider_config()
    client = _get_client()
    if cfg["format"] == "anthropic":
        # 注意: anthropic SDK 2.x 的 messages.create 已移除 temperature 参数, 不能传
        system, msgs = _split_system(messages)
        resp = client.messages.create(
            model=cfg["model"], system=system or None, messages=msgs,
            max_tokens=max_tokens,
        )
        return _text_from_anthropic_content(resp.content)

    kwargs = dict(model=cfg["model"], messages=messages, temperature=temperature, max_tokens=max_tokens)
    if force_json:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as e:
        if force_json and "response_format" in str(e):
            kwargs.pop("response_format", None)
            resp = client.chat.completions.create(**kwargs)
        else:
            raise
    return resp.choices[0].message.content.strip()


def stream_chat(messages: list, temperature: float = 0.3, max_tokens: int = 2048):
    """流式对话, 逐段 yield 文本增量 (两种协议统一为纯文本增量)."""
    cfg = get_provider_config()
    client = _get_client()
    if cfg["format"] == "anthropic":
        system, msgs = _split_system(messages)
        with client.messages.stream(model=cfg["model"], system=system or None, messages=msgs,
                                    max_tokens=max_tokens) as stream:
            for text in stream.text_stream:
                if text:
                    yield text
    else:
        resp = client.chat.completions.create(
            model=cfg["model"], messages=messages, temperature=temperature,
            max_tokens=max_tokens, stream=True,
        )
        for chunk in resp:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content


def vision_completion(prompt: str, image_b64: str, mime_type: str,
                      temperature: float = 0.2, max_tokens: int = 16000) -> str:
    """带图片输入的补全, 返回文本."""
    cfg = get_provider_config()
    client = _get_client()
    if cfg["format"] == "anthropic":
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": image_b64}},
            {"type": "text", "text": prompt},
        ]
        kwargs = dict(model=cfg["model"], messages=[{"role": "user", "content": content}],
                      max_tokens=max_tokens)
        # 思考型模型 (GLM 5.x / Claude) 会把 token 耗在思考块上, 大任务禁用思考保证输出
        try:
            resp = client.messages.create(**kwargs, thinking={"type": "disabled"})
        except Exception:
            resp = client.messages.create(**kwargs)
        return _text_from_anthropic_content(resp.content)

    data_uri = f"data:{mime_type};base64,{image_b64}"
    resp = client.chat.completions.create(
        model=cfg["model"], temperature=temperature, max_tokens=max_tokens,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": data_uri}},
            {"type": "text", "text": prompt},
        ]}],
    )
    return resp.choices[0].message.content.strip()


def list_models() -> list:
    """从服务商接口自动获取可用模型列表."""
    cfg = get_provider_config()
    if not cfg["api_key"]:
        raise ValueError("API Key 未配置，无法获取模型列表")
    client = _get_client()
    models = []
    if cfg["format"] == "anthropic":
        for m in client.models.list():
            models.append(getattr(m, "id", None) or getattr(m, "name", ""))
    else:
        for m in client.models.list():
            models.append(getattr(m, "id", None) or getattr(m, "name", ""))
    return sorted({x for x in models if x})
