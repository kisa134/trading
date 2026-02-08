"""
LLM providers: OpenRouter (REST), Google Gemini (REST generateContent).
Async functions; used by router and AI controller.
"""
import os
import json
import base64
from typing import Any

import httpx

from .config import (
    OPENROUTER_BASE,
    OPENROUTER_API_KEY,
    GOOGLE_API_KEY,
    MULTIMODAL_FALLBACK_MODEL,
    DEEPSEEK_METRICS_MODEL,
    VMAMBA_SERVICE_URL,
)


async def openrouter_chat(
    messages: list[dict[str, Any]],
    model_id: str,
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> str:
    """OpenRouter chat completions (no stream). Returns assistant text."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    url = f"{OPENROUTER_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.environ.get("APP_URL", "http://localhost:8000"),
    }
    body = {
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    choice = (data.get("choices") or [None])[0]
    if not choice:
        raise ValueError("No choices in OpenRouter response")
    return (choice.get("message") or {}).get("content") or ""


async def openrouter_multimodal(
    messages: list[dict[str, Any]],
    model_id: str | None = None,
    max_tokens: int = 2048,
) -> str:
    """OpenRouter with optional image (base64 in content). messages may include content parts with type image_url."""
    model_id = model_id or "openai/gpt-4o"
    return await openrouter_chat(messages, model_id, max_tokens=max_tokens)


def _build_gemini_part(text: str | None = None, inline_data_base64: str | None = None, mime: str = "image/jpeg") -> dict:
    part: dict = {}
    if text:
        part["text"] = text
    if inline_data_base64:
        part["inlineData"] = {"mimeType": mime, "data": inline_data_base64}
    return part


async def gemini_generate_content(
    contents: list[dict[str, Any]],
    model: str = "gemini-1.5-flash",
    max_output_tokens: int = 2048,
    cached_content_name: str | None = None,
) -> str:
    """Google Gemini generateContent (REST). Optional cached_content_name from Context Caching."""
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY not set")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GOOGLE_API_KEY}"
    body = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_output_tokens,
            "temperature": 0.3,
        },
    }
    if cached_content_name:
        body["cachedContent"] = cached_content_name
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=body)
        r.raise_for_status()
        data = r.json()
    candidates = (data.get("candidates") or [None])[0]
    if not candidates:
        raise ValueError("No candidates in Gemini response")
    parts = candidates.get("content", {}).get("parts", [])
    return " ".join((p.get("text") or "") for p in parts)


async def gemini_multimodal(
    text: str,
    image_base64: str | None = None,
    model: str = "gemini-1.5-flash",
    cached_content_name: str | None = None,
) -> str:
    """Single turn: text + optional image -> model response. Optional cached_content_name."""
    parts = [{"text": text}]
    if image_base64:
        parts.append({"inlineData": {"mimeType": "image/jpeg", "data": image_base64}})
    contents = [{"role": "user", "parts": parts}]
    return await gemini_generate_content(contents, model=model, cached_content_name=cached_content_name)


async def deepseek_metrics_plan(metrics_json: str, system_prompt: str | None = None) -> str:
    """DeepSeek V3 via OpenRouter: analyze Delta, OI, Funding, liquidations; return trade plan."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    default_system = (
        "You are a quantitative analyst. Given JSON with market metrics (delta, open interest, "
        "funding rate, liquidations), produce a short trade plan: bias, key levels, risk."
    )
    messages: list[dict[str, Any]] = []
    messages.append({"role": "system", "content": system_prompt or default_system})
    messages.append({"role": "user", "content": f"Analyze and give a trade plan:\n{metrics_json}"})
    return await openrouter_chat(messages, model_id=DEEPSEEK_METRICS_MODEL, max_tokens=1024)


async def vmamba_tick_anomaly(trades_window: list[dict]) -> float | None:
    """Optional: call Visual Mamba service (Docker) for anomaly score on tick window. Returns 0..1 or None."""
    if not VMAMBA_SERVICE_URL:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                f"{VMAMBA_SERVICE_URL.rstrip('/')}/score",
                json={"trades": trades_window},
            )
            if r.status_code != 200:
                return None
            data = r.json()
            return float(data.get("anomaly_score", data.get("score", 0)))
    except Exception:
        return None
