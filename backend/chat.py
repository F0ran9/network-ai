import json
import llm_client
from fastapi.responses import StreamingResponse
from prompts import CHAT_SYSTEM_PROMPT, VENDOR_STYLES

def reset_client():
    """配置更新后使缓存的客户端失效."""
    llm_client.reset_client()


def build_system_prompt(topology, vendor, configs):
    vendor = vendor.capitalize()
    style = VENDOR_STYLES.get(vendor, VENDOR_STYLES["default"])
    topo_str = json.dumps(topology, ensure_ascii=False, indent=2)
    configs_str = json.dumps(configs, ensure_ascii=False, indent=2) if configs else "尚未生成配置"
    return CHAT_SYSTEM_PROMPT.format(
        topology_context=topo_str,
        vendor=vendor,
        style=style,
        configs_context=configs_str,
    )


async def stream_chat(messages: list, topology: dict, vendor: str, configs: dict):
    system_prompt = build_system_prompt(topology, vendor, configs)
    api_messages = [{"role": "system", "content": system_prompt}] + messages

    response = llm_client.stream_chat(api_messages, temperature=0.3, max_tokens=2048)
    for token in response:
        if token:
            yield f"data: {json.dumps({'token': token})}\n\n"

    yield "data: [DONE]\n\n"
