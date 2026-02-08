"""
Gemini Context Caching: cache heavy system prompt + instructions to reduce token cost.
Creates cachedContent via REST, stores name in Redis; providers use it when calling Gemini.
"""
import os
import sys
import json
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import httpx

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
REDIS_KEY_GEMINI_CACHE_NAME = "ai:gemini_cached_content_name"
CACHE_TTL_SEC = 3600  # 1 hour
GEMINI_CACHE_MODEL = "gemini-1.5-flash"


def build_system_prompt_text() -> str:
    """Heavy part: system instructions and Bookmap pattern descriptions (unchanged often)."""
    return """You are a professional trading analyst. Analyze the provided market context and heatmap image.
Focus on: order flow (tape deltas), footprint imbalances, heatmap density, and recent events (icebergs, walls).
Give concise assessment and, if appropriate, a short-term bias (direction and key levels).
Do not give financial advice; this is for educational and research use only."""


async def create_gemini_cache(system_text: str) -> str | None:
    """Create cachedContent via Gemini REST API. Returns cached content name or None."""
    if not GOOGLE_API_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/cachedContents?key={GOOGLE_API_KEY}"
    body = {
        "model": f"models/{GEMINI_CACHE_MODEL}",
        "systemInstruction": {"parts": [{"text": system_text}]},
        "ttl": "3600s",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
        return data.get("name")
    except Exception as e:
        print(f"[context_caching] create_gemini_cache: {e}")
        return None


async def get_or_refresh_cache_name(redis_client) -> str | None:
    """Return cached content name from Redis, or create new cache and store it."""
    name = await redis_client.get(REDIS_KEY_GEMINI_CACHE_NAME)
    if name:
        return name
    text = build_system_prompt_text()
    name = await create_gemini_cache(text)
    if name:
        await redis_client.set(REDIS_KEY_GEMINI_CACHE_NAME, name, ex=CACHE_TTL_SEC)
    return name
