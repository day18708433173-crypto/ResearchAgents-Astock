"""LLM 客户端（支持 DeepSeek / MiMo 等模型）

性能优化：config 和 client 模块级缓存，避免每次 chat() 重复读取 YAML 和创建连接。
"""
from collections.abc import AsyncIterator, Iterator
from typing import Literal

import yaml
from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI
from pathlib import Path

# ── 启动时加载 .env 文件到环境变量 ──
load_dotenv(Path(__file__).parent.parent / ".env")

Scenario = Literal["default", "debate", "coach"]

# ── 模块级缓存：config 和 client 只初始化一次 ──
_cached_config: dict | None = None
_cached_client: OpenAI | None = None
_cached_async_client: AsyncOpenAI | None = None


def get_llm_config() -> dict:
    """获取 LLM 配置（模块级缓存，只读一次 YAML）。"""
    global _cached_config
    if _cached_config is not None:
        return _cached_config
    import os
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        raw = f.read()
    # 替换 ${VAR} 为环境变量值（dotenv 已加载 .env）
    for key, val in os.environ.items():
        raw = raw.replace(f"${{{key}}}", val)
    config = yaml.safe_load(raw)
    _cached_config = config["llm"]
    return _cached_config


def _get_max_tokens(scenario: Scenario = "default") -> int:
    cfg = get_llm_config()
    if scenario == "debate":
        return cfg.get("max_tokens_debate", 1024)
    if scenario == "coach":
        return cfg.get("max_tokens_coach", 2048)
    return cfg.get("max_tokens", 4096)


def _build_messages(prompt: str, system: str = "") -> list[dict]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


def create_client() -> OpenAI:
    """创建/复用 LLM 客户端（模块级缓存）。"""
    global _cached_client
    if _cached_client is not None:
        return _cached_client
    cfg = get_llm_config()
    _cached_client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
    return _cached_client


def create_async_client() -> AsyncOpenAI:
    """创建/复用异步 LLM 客户端。"""
    global _cached_async_client
    if _cached_async_client is not None:
        return _cached_async_client
    cfg = get_llm_config()
    _cached_async_client = AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
    return _cached_async_client


def chat(
    prompt: str,
    system: str = "",
    use_reasoning: bool = False,
    scenario: Scenario = "default",
) -> str:
    """单轮对话，返回文本内容。use_reasoning=True时使用强推理模型。"""
    cfg = get_llm_config()
    client = create_client()
    model = cfg["reasoning_model"] if use_reasoning else cfg["model"]
    resp = client.chat.completions.create(
        model=model,
        messages=_build_messages(prompt, system),
        max_tokens=_get_max_tokens(scenario),
        temperature=cfg.get("temperature", 0.7),
    )
    return resp.choices[0].message.content


def chat_with_search(prompt: str, system: str = "") -> str:
    """带联网搜索的单轮对话。DeepSeek 会实时检索互联网获取最新信息。"""
    cfg = get_llm_config()
    client = create_client()
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=_build_messages(prompt, system),
        max_tokens=cfg.get("max_tokens", 4096),
        temperature=cfg.get("temperature", 0.7),
        extra_body={"enable_search": True},
    )
    return resp.choices[0].message.content


def stream_chat(
    prompt: str,
    system: str = "",
    use_reasoning: bool = False,
    scenario: Scenario = "default",
) -> Iterator[str]:
    """流式对话，返回生成器。use_reasoning=True时使用强推理模型。"""
    cfg = get_llm_config()
    client = create_client()
    model = cfg["reasoning_model"] if use_reasoning else cfg["model"]
    stream = client.chat.completions.create(
        model=model,
        messages=_build_messages(prompt, system),
        max_tokens=_get_max_tokens(scenario),
        temperature=cfg.get("temperature", 0.7),
        stream=True,
    )
    for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


async def astream_chat(
    prompt: str,
    system: str = "",
    use_reasoning: bool = False,
    scenario: Scenario = "default",
) -> AsyncIterator[str]:
    """异步流式对话，供 FastAPI SSE 使用。"""
    cfg = get_llm_config()
    client = create_async_client()
    model = cfg["reasoning_model"] if use_reasoning else cfg["model"]
    stream = await client.chat.completions.create(
        model=model,
        messages=_build_messages(prompt, system),
        max_tokens=_get_max_tokens(scenario),
        temperature=cfg.get("temperature", 0.7),
        stream=True,
    )
    async for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
