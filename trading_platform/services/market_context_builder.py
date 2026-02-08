"""
Market context builder: reads tape, heatmap, footprint, events, scores from Redis,
aggregates into structured text for LLM prompts, caches in Redis (ai:context:{exchange}:{symbol}).
"""
import asyncio
import json
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import redis.asyncio as redis

from shared.streams import (
    REDIS_KEY_TAPE,
    REDIS_KEY_HEATMAP,
    REDIS_KEY_FOOTPRINT,
    REDIS_KEY_EVENTS,
    REDIS_KEY_SCORES_TREND,
    REDIS_KEY_SCORES_EXHAUSTION,
    REDIS_KEY_SIGNALS_RULE,
    REDIS_KEY_AI_CONTEXT,
    AI_CONTEXT_TTL_SEC,
    SCORES_MAXLEN,
    SIGNALS_MAXLEN,
)

HEATMAP_LAST_N = 10
FOOTPRINT_LAST_N = 10
EVENTS_LAST_N = 20


def _ts_to_str(ts: int) -> str:
    if not ts:
        return ""
    try:
        if ts > 1e12:
            ts = ts / 1000.0
        return datetime.utcfromtimestamp(ts).strftime("%H:%M:%S")
    except Exception:
        return str(ts)


async def build_market_context(r: redis.Redis, exchange: str, symbol: str) -> str:
    """Read Redis keys for (exchange, symbol), return single structured text."""
    parts = []

    # Tape (current aggregates + last trade)
    tape_key = REDIS_KEY_TAPE.format(exchange=exchange, symbol=symbol)
    tape_raw = await r.get(tape_key)
    if tape_raw:
        try:
            tape = json.loads(tape_raw)
            parts.append("=== TAPE (order flow) ===")
            parts.append(f"Last update: {_ts_to_str(tape.get('ts', 0))}")
            agg = tape.get("aggregates", {})
            for label, v in agg.items():
                parts.append(
                    f"  {label}: buy_vol={v.get('buy_vol', 0):.0f} sell_vol={v.get('sell_vol', 0):.0f} delta={v.get('delta', 0):.0f}"
                )
            lt = tape.get("last_trade", {})
            if lt:
                large = " [LARGE]" if lt.get("large") else ""
                parts.append(f"  Last trade: {lt.get('side')} {lt.get('price')} size={lt.get('size')}{large}")
            parts.append("")
        except json.JSONDecodeError:
            pass

    # Heatmap: last N slices summary
    heatmap_key = REDIS_KEY_HEATMAP.format(exchange=exchange, symbol=symbol)
    heatmap_items = await r.lrange(heatmap_key, -HEATMAP_LAST_N, -1)
    if heatmap_items:
        parts.append("=== HEATMAP (last slices) ===")
        for raw in heatmap_items[-5:]:
            try:
                s = json.loads(raw)
                ts = s.get("ts", 0)
                rows = s.get("rows", [])
                total_bid = sum(r.get("vol_bid", 0) for r in rows)
                total_ask = sum(r.get("vol_ask", 0) for r in rows)
                parts.append(f"  {_ts_to_str(ts)} rows={len(rows)} vol_bid={total_bid:.0f} vol_ask={total_ask:.0f}")
            except (json.JSONDecodeError, TypeError):
                continue
        parts.append("")

    # Footprint: last N bars (delta per bar)
    fp_key = REDIS_KEY_FOOTPRINT.format(exchange=exchange, symbol=symbol)
    fp_items = await r.lrange(fp_key, -FOOTPRINT_LAST_N, -1)
    if fp_items:
        parts.append("=== FOOTPRINT (last bars) ===")
        for raw in fp_items[-5:]:
            try:
                bar = json.loads(raw)
                start = bar.get("start", 0)
                levels = bar.get("levels", [])
                delta_sum = sum(l.get("delta", 0) for l in levels)
                parts.append(f"  {_ts_to_str(start)} levels={len(levels)} bar_delta={delta_sum:.0f}")
            except (json.JSONDecodeError, TypeError):
                continue
        parts.append("")

    # Events (iceberg, wall, spoof, etc.)
    events_key = REDIS_KEY_EVENTS.format(exchange=exchange, symbol=symbol)
    events_items = await r.lrange(events_key, -EVENTS_LAST_N, -1)
    if events_items:
        parts.append("=== EVENTS ===")
        for raw in events_items[-10:]:
            try:
                e = json.loads(raw)
                etype = e.get("type", "?")
                ts = e.get("ts", e.get("ts_start", 0))
                price = e.get("price")
                side = e.get("side", "")
                vol = e.get("volume", "")
                parts.append(f"  {_ts_to_str(ts)} {etype} price={price} side={side} vol={vol}")
            except (json.JSONDecodeError, TypeError):
                continue
        parts.append("")

    # Trend scores
    trend_key = REDIS_KEY_SCORES_TREND.format(exchange=exchange, symbol=symbol)
    trend_items = await r.lrange(trend_key, -min(SCORES_MAXLEN, 10), -1)
    if trend_items:
        parts.append("=== TREND SCORES ===")
        for raw in trend_items[-5:]:
            try:
                s = json.loads(raw)
                parts.append(
                    f"  {_ts_to_str(s.get('ts'))} trend_power={s.get('trend_power', 0):.3f} delta={s.get('trend_power_delta', 0):.3f}"
                )
            except (json.JSONDecodeError, TypeError):
                continue
        parts.append("")

    # Exhaustion
    exh_key = REDIS_KEY_SCORES_EXHAUSTION.format(exchange=exchange, symbol=symbol)
    exh_items = await r.lrange(exh_key, -min(SCORES_MAXLEN, 10), -1)
    if exh_items:
        parts.append("=== EXHAUSTION / ABSORPTION ===")
        for raw in exh_items[-5:]:
            try:
                s = json.loads(raw)
                parts.append(
                    f"  {_ts_to_str(s.get('ts'))} exhaustion={s.get('exhaustion_score', 0):.3f} absorption={s.get('absorption_score', 0):.3f}"
                )
            except (json.JSONDecodeError, TypeError):
                continue
        parts.append("")

    # Rule reversal signals
    sig_key = REDIS_KEY_SIGNALS_RULE.format(exchange=exchange, symbol=symbol)
    sig_items = await r.lrange(sig_key, -min(SIGNALS_MAXLEN, 5), -1)
    if sig_items:
        parts.append("=== REVERSAL SIGNALS ===")
        for raw in sig_items[-3:]:
            try:
                s = json.loads(raw)
                rng = s.get("expected_move_range", [])
                parts.append(
                    f"  {_ts_to_str(s.get('ts'))} prob_reversal={s.get('prob_reversal_rule', 0):.2f} horizon_bars={s.get('reversal_horizon_bars')} range={rng}"
                )
            except (json.JSONDecodeError, TypeError):
                continue
        parts.append("")

    text = "\n".join(parts).strip()
    return text or "(No market data yet)"


async def get_or_build_context(r: redis.Redis, exchange: str, symbol: str) -> str:
    """Return cached context if present and not expired, else build and cache."""
    key = REDIS_KEY_AI_CONTEXT.format(exchange=exchange, symbol=symbol)
    cached = await r.get(key)
    if cached:
        return cached
    text = await build_market_context(r, exchange, symbol)
    await r.set(key, text, ex=AI_CONTEXT_TTL_SEC)
    return text


async def run_worker(redis_url: str, refresh_interval_sec: float = 10.0):
    """Background worker: refresh context for pairs that have recent snapshot/activity.
    Expects Redis set 'ai:active_pairs' with members 'exchange:symbol' (populated by API on snapshot).
    """
    r = redis.from_url(redis_url, decode_responses=True)
    while True:
        try:
            pairs_raw = await r.smembers("ai:active_pairs")
            for member in pairs_raw or []:
                if ":" in member:
                    exchange, symbol = member.split(":", 1)
                    ctx = await build_market_context(r, exchange, symbol)
                    key = REDIS_KEY_AI_CONTEXT.format(exchange=exchange, symbol=symbol)
                    await r.set(key, ctx, ex=AI_CONTEXT_TTL_SEC)
            await asyncio.sleep(refresh_interval_sec)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[market_context_builder] Error: {e}")
            await asyncio.sleep(5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379", help="Redis URL")
    parser.add_argument("--interval", type=float, default=10.0, help="Refresh interval seconds")
    args = parser.parse_args()
    asyncio.run(run_worker(args.redis, args.interval))


if __name__ == "__main__":
    main()
