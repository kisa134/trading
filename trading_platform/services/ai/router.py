"""
LLM router: dispatch by request type (multimodal_live, text_analyst, aggregator, tick_anomaly).
Returns text response; tick_anomaly is handled by Visual Mamba worker (not HTTP).
"""
from typing import Any

from .config import (
    get_model_for_role,
    get_multimodal_model,
    MODELS,
    MULTIMODAL_FALLBACK_MODEL,
    DEEPSEEK_REFLECTION_MODEL,
)
from . import providers

COGNITIVE_SYSTEM_PROMPT = (
    "You are a trading analyst. Use structured reasoning in <think>...</think> tags: "
    "first state the facts (DOM, tape, footprint, events), then your hypothesis, "
    "then check for spoofing or anomalies. After the think block, give a short "
    "actionable conclusion (entry/exit/avoid and why). If you revise your view, "
    'say so explicitly in <think> (e.g. "revising: possible spoof").'
)


async def route_text_analyst(text: str, system_prompt: str | None = None) -> str:
    """Events/logs analysis -> DeepSeek."""
    model = get_model_for_role("text_analyst")
    if not model or model["provider"] != "openrouter":
        return ""
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": text})
    return await providers.openrouter_chat(messages, model["model_id"])


async def route_aggregator(text: str, system_prompt: str | None = None) -> str:
    """Structured data / tables -> Qwen."""
    model = get_model_for_role("aggregator")
    if not model or model["provider"] != "openrouter":
        return ""
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": text})
    return await providers.openrouter_chat(messages, model["model_id"])


async def route_reflection(prompt: str) -> str:
    """Self-reflection (why did prediction fail?) -> DeepSeek R1."""
    model = get_model_for_role("reflection")
    if not model or model["provider"] != "openrouter":
        return ""
    messages = [{"role": "user", "content": prompt}]
    return await providers.openrouter_chat(messages, DEEPSEEK_REFLECTION_MODEL, max_tokens=1024)


def parse_think_blocks(text: str) -> list[str]:
    """Extract <think>...</think> blocks from R1 response. Returns list of inner content."""
    import re
    blocks = re.findall(r"<think>\s*(.*?)\s*</think>", text, re.DOTALL | re.IGNORECASE)
    return [b.strip() for b in blocks]


def has_doubt_or_revision(text: str) -> bool:
    """True if response suggests revision, anomaly, or spoof concern (Aha moment)."""
    lower = text.lower()
    markers = ("revising", "reconsider", "аномал", "anomaly", "спуфинг", "spoof", "пересмотр", "doubt", "осторожн")
    return any(m in lower for m in markers)


async def route_cognitive_analyst(
    text: str,
    system_prompt: str | None = None,
    graph_context: str | None = None,
) -> str:
    """Strategic analyst: DeepSeek R1 with <think> and GraphRAG context."""
    model = get_model_for_role("cognitive_analyst")
    if not model or model["provider"] != "openrouter":
        return ""
    sys_content = system_prompt or COGNITIVE_SYSTEM_PROMPT
    if graph_context:
        sys_content = f"{sys_content}\n\nGraph memory (past similar situations and levels):\n{graph_context}"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": sys_content},
        {"role": "user", "content": text},
    ]
    return await providers.openrouter_chat(messages, model["model_id"], max_tokens=2048)


async def route_multimodal(
    text: str,
    image_base64: str | None = None,
    use_gemini_first: bool = True,
    cached_content_name: str | None = None,
) -> str:
    """Snapshot + context -> Gemini or OpenRouter vision. Fallback to OpenRouter if Gemini fails."""
    if use_gemini_first and providers.GOOGLE_API_KEY:
        try:
            return await providers.gemini_multimodal(text, image_base64, cached_content_name=cached_content_name)
        except Exception:
            pass
    # Fallback: OpenRouter vision
    messages: list[dict[str, Any]] = [{"role": "user", "content": []}]
    content = messages[0]["content"]
    if image_base64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
        })
    content.append({"type": "text", "text": text})
    return await providers.openrouter_multimodal(messages, model_id=MULTIMODAL_FALLBACK_MODEL)


async def route_metrics_plan(metrics_json: str, system_prompt: str | None = None) -> str:
    """Delta, OI, funding, liquidations JSON -> DeepSeek V3 trade plan."""
    return await providers.deepseek_metrics_plan(metrics_json, system_prompt=system_prompt)
