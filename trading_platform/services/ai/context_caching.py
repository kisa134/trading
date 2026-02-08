"""
Gemini Context Caching: cache system prompt + last N ticks (tape summary) to reduce token cost.
Creates cachedContent via REST, stores name in Redis per (exchange, symbol); providers use it when calling Gemini.
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
TAPE_CACHE_TRADES_MAX = 500  # last N trades to include in cache (cap token size)


def build_system_prompt_text() -> str:
    """Heavy part: system instructions and Bookmap pattern descriptions (unchanged often)."""
    return """You are a professional trading analyst. Analyze the provided market context and heatmap image.
Focus on: order flow (tape deltas), footprint imbalances, heatmap density, and recent events (icebergs, walls).
Give concise assessment and, if appropriate, a short-term bias (direction and key levels).
Do not give financial advice; this is for educational and research use only."""


async def build_tape_summary_for_cache(redis_client, exchange: str, symbol: str) -> str:
    """Build compact text summary of last N trades for cached content."""
    from shared.streams import REDIS_KEY_TRADES
    key = REDIS_KEY_TRADES.format(exchange=exchange, symbol=symbol)
    items = await redis_client.lrange(key, -TAPE_CACHE_TRADES_MAX, -1)
    if not items:
        return ""
    lines = ["Last tape (ts price side size):"]
    for raw in items[-TAPE_CACHE_TRADES_MAX:]:
        try:
            t = json.loads(raw)
            ts = t.get("ts", 0)
            price = t.get("price", 0)
            side = t.get("side", "")
            size = t.get("size", 0)
            lines.append(f"  {ts} {price} {side} {size}")
        except (json.JSONDecodeError, TypeError):
            continue
    return "\n".join(lines) if len(lines) > 1 else ""


async def create_gemini_cache(system_text: str, contents_text: str | None = None) -> str | None:
    """Create cachedContent via Gemini REST API. Optionally include contents (e.g. tape summary). Returns cached content name or None."""
    if not GOOGLE_API_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/cachedContents?key={GOOGLE_API_KEY}"
    body = {
        "model": f"models/{GEMINI_CACHE_MODEL}",
        "systemInstruction": {"parts": [{"text": system_text}]},
        "ttl": "3600s",
    }
    if contents_text and len(contents_text.strip()) > 0:
        body["contents"] = [{"role": "user", "parts": [{"text": contents_text[:50000]}]}]
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
        return data.get("name")
    except Exception as e:
        print(f"[context_caching] create_gemini_cache: {e}")
        return None


def _cache_key(exchange: str | None, symbol: str | None) -> str:
    if exchange and symbol:
        return f"{REDIS_KEY_GEMINI_CACHE_NAME}:{exchange}:{symbol}"
    return REDIS_KEY_GEMINI_CACHE_NAME


async def get_or_refresh_cache_name(redis_client, exchange: str | None = None, symbol: str | None = None) -> str | None:
    """Return cached content name from Redis, or create new cache (system + optional tape for pair) and store it."""
    key = _cache_key(exchange, symbol)
    name = await redis_client.get(key)
    if name:
        return name
    text = build_system_prompt_text()
    contents_text = ""
    if exchange and symbol:
        contents_text = await build_tape_summary_for_cache(redis_client, exchange, symbol)
    name = await create_gemini_cache(text, contents_text=contents_text if contents_text else None)
    if name:
        await redis_client.set(key, name, ex=CACHE_TTL_SEC)
    return name
