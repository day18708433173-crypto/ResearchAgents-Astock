"""LLM 客户端（支持 DeepSeek / MiMo 等模型）

性能优化：config 和 client 模块级缓存，避免每次 chat() 重复读取 YAML 和创建连接。
"""
from collections.abc import AsyncIterator, Iterator
from typing import Literal, Mapping

import yaml
from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI
from pathlib import Path

# ── 启动时加载 .env 文件到环境变量 ──
load_dotenv(Path(__file__).parent.parent / ".env")

Scenario = Literal["default", "debate", "coach", "judge", "knowledge"]

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
    if scenario == "judge":
        return cfg.get("max_tokens_judge", 1200)
    if scenario == "knowledge":
        return cfg.get("max_tokens_knowledge", 768)
    return cfg.get("max_tokens", 4096)


def _build_messages(prompt: str, system: str = "") -> list[dict]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


def _select_model(cfg: dict, scenario: Scenario = "default", use_reasoning: bool = False) -> str:
    """裁判等强推理场景优先使用 reasoning_model。"""
    if use_reasoning or scenario == "judge":
        reasoning = (cfg.get("reasoning_model") or "").strip()
        if reasoning:
            return reasoning
    model = (cfg.get("model") or "").strip()
    if not model:
        raise ValueError("LLM model 未配置")
    return model


def _strip_think_tags(text: str) -> str:
    """剥除推理模型内联的 <think>...</think> 思考链，只保留正文。"""
    import re
    text = re.sub(r"<think\b[^>]*>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<thinking\b[^>]*>[\s\S]*?</thinking>", "", text, flags=re.IGNORECASE)
    return text.strip()


def _message_text(message) -> str:
    """提取 assistant 文本；兼容 reasoning 模型把正文放在 reasoning_content 的情况。

    部分代理/模型会把思考链内联在 content 里（<think>...</think>），
    这里统一剥除，只返回最终正文。
    """
    content = (getattr(message, "content", None) or "").strip()
    if content:
        cleaned = _strip_think_tags(content)
        return cleaned if cleaned else content  # 若全是思考链则保留原文避免空返回
    reasoning = getattr(message, "reasoning_content", None)
    if reasoning and str(reasoning).strip():
        return str(reasoning).strip()
    return ""


def _resolve_config(llm_config: Mapping[str, str] | None = None) -> dict:
    """Merge request-scoped LLM config over the default YAML config."""
    cfg = dict(get_llm_config())
    if llm_config:
        for key in ("api_key", "base_url", "model", "reasoning_model"):
            value = (llm_config.get(key) or "").strip()
            if value:
                cfg[key] = value
        # 用户只配置了 model 时，裁判与辩论共用同一模型，避免误用 YAML 默认 reasoning_model
        if (llm_config.get("model") or "").strip() and not (llm_config.get("reasoning_model") or "").strip():
            cfg["reasoning_model"] = cfg["model"]
    return cfg


def create_client(llm_config: Mapping[str, str] | None = None) -> OpenAI:
    """创建/复用 LLM 客户端（模块级缓存）。"""
    if llm_config:
        cfg = _resolve_config(llm_config)
        return OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])

    global _cached_client
    if _cached_client is not None:
        return _cached_client
    cfg = get_llm_config()
    _cached_client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
    return _cached_client


def create_async_client(llm_config: Mapping[str, str] | None = None) -> AsyncOpenAI:
    """创建/复用异步 LLM 客户端。"""
    if llm_config:
        cfg = _resolve_config(llm_config)
        return AsyncOpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])

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
    llm_config: Mapping[str, str] | None = None,
) -> str:
    """单轮对话，返回文本内容。use_reasoning=True时使用强推理模型。"""
    cfg = _resolve_config(llm_config)
    client = create_client(llm_config)
    model = _select_model(cfg, scenario, use_reasoning)
    resp = client.chat.completions.create(
        model=model,
        messages=_build_messages(prompt, system),
        max_tokens=_get_max_tokens(scenario),
        temperature=cfg.get("temperature", 0.7),
    )
    text = _message_text(resp.choices[0].message)
    if not text:
        finish = getattr(resp.choices[0], "finish_reason", None)
        raise ValueError(f"LLM 返回空内容 (finish_reason={finish!r}, model={model})")
    return text


def chat_with_search(
    prompt: str,
    system: str = "",
    llm_config: Mapping[str, str] | None = None,
) -> str:
    """带联网搜索的单轮对话。DeepSeek 会实时检索互联网获取最新信息。"""
    cfg = _resolve_config(llm_config)
    client = create_client(llm_config)
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
    llm_config: Mapping[str, str] | None = None,
) -> Iterator[str]:
    """流式对话，返回生成器。use_reasoning=True时使用强推理模型。"""
    cfg = _resolve_config(llm_config)
    client = create_client(llm_config)
    model = _select_model(cfg, scenario, use_reasoning)
    stream = client.chat.completions.create(
        model=model,
        messages=_build_messages(prompt, system),
        max_tokens=_get_max_tokens(scenario),
        temperature=cfg.get("temperature", 0.7),
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning:
            yield reasoning


async def astream_chat(
    prompt: str,
    system: str = "",
    use_reasoning: bool = False,
    scenario: Scenario = "default",
    llm_config: Mapping[str, str] | None = None,
) -> AsyncIterator[str]:
    """异步流式对话，供 FastAPI SSE 使用。"""
    cfg = _resolve_config(llm_config)
    client = create_async_client(llm_config)
    model = _select_model(cfg, scenario, use_reasoning)
    stream = await client.chat.completions.create(
        model=model,
        messages=_build_messages(prompt, system),
        max_tokens=_get_max_tokens(scenario),
        temperature=cfg.get("temperature", 0.7),
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning:
            yield reasoning
