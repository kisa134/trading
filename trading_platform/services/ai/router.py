"""
LLM router: dispatch by request type (multimodal_live, text_analyst, aggregator, tick_anomaly).
Returns text response; tick_anomaly is handled by Visual Mamba worker (not HTTP).
"""
from typing import Any

from .config import get_model_for_role, get_multimodal_model, MODELS, MULTIMODAL_FALLBACK_MODEL
from . import providers


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
    return await providers.openrouter_chat(messages, model["model_id"], max_tokens=1024)


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
