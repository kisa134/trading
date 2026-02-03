"""
Exhaustion / Absorption engine: computes scores from trades and orderbook slices.
Publishes to scores.exhaustion stream and Redis list.
"""
import asyncio
import json
import argparse
import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import redis.asyncio as redis

from shared.streams import (
    STREAM_SCORES_EXHAUSTION,
    REDIS_KEY_TRADES,
    REDIS_KEY_ORDERBOOK_SLICES,
    REDIS_KEY_SCORES_EXHAUSTION,
    SCORES_MAXLEN,
)

BAR_MS = 60000
WALL_RATIO_THRESHOLD = 3.0


def _compute_bar(trades: list[dict]) -> dict:
    prices = [t.get("price", 0) for t in trades]
    if not prices:
        return {}
    o = prices[0]
    h = max(prices)
    lo = min(prices)
    c = prices[-1]
    buy = sum(t.get("size", t.get("volume", 0)) for t in trades if (t.get("side") or "").lower() in ("buy", "bid"))
    sell = sum(t.get("size", t.get("volume", 0)) for t in trades if (t.get("side") or "").lower() not in ("buy", "bid"))
    delta = buy - sell
    return {"open": o, "high": h, "low": lo, "close": c, "delta": delta}


async def run_exhaustion_engine(redis_url: str, exchange: str, symbol: str):
    r = redis.from_url(redis_url, decode_responses=True)
    trades_key = REDIS_KEY_TRADES.format(exchange=exchange, symbol=symbol)
    slices_key = REDIS_KEY_ORDERBOOK_SLICES.format(exchange=exchange, symbol=symbol)
    scores_key = REDIS_KEY_SCORES_EXHAUSTION.format(exchange=exchange, symbol=symbol)

    while True:
        try:
            raw_trades = await r.lrange(trades_key, -2000, -1)
            trades = []
            for x in raw_trades or []:
                try:
                    trades.append(json.loads(x))
                except json.JSONDecodeError:
                    pass
            if len(trades) < 10:
                await asyncio.sleep(1)
                continue
            latest_ts = max(t.get("ts", 0) for t in trades)
            curr_start = (latest_ts // BAR_MS) * BAR_MS
            prev_start = curr_start - BAR_MS
            curr_trades = [t for t in trades if curr_start <= t.get("ts", 0) < curr_start + BAR_MS]
            prev_trades = [t for t in trades if prev_start <= t.get("ts", 0) < prev_start + BAR_MS]
            curr_bar = _compute_bar(curr_trades)
            prev_bar = _compute_bar(prev_trades)
            if not curr_bar or not prev_bar:
                await asyncio.sleep(1)
                continue

            exhaustion = 0.0
            # exhaustion: new high/low with weaker delta
            if curr_bar["high"] > prev_bar["high"] and abs(curr_bar["delta"]) < abs(prev_bar["delta"]) * 0.5:
                exhaustion = 70.0
            if curr_bar["low"] < prev_bar["low"] and abs(curr_bar["delta"]) < abs(prev_bar["delta"]) * 0.5:
                exhaustion = max(exhaustion, 70.0)
            # divergence: price extends but delta drops
            if (curr_bar["close"] > prev_bar["close"] and curr_bar["delta"] < prev_bar["delta"] * 0.5) or (
                curr_bar["close"] < prev_bar["close"] and curr_bar["delta"] > prev_bar["delta"] * 0.5
            ):
                exhaustion = max(exhaustion, 60.0)

            # absorption: large wall + small range + heavy delta
            absorption = 0.0
            raw_slice = await r.lrange(slices_key, -1, -1)
            wall_ratio = 0.0
            if raw_slice:
                try:
                    snap = json.loads(raw_slice[0])
                    sizes = [float(s) for _, s in (snap.get("bids", [])[:20] + snap.get("asks", [])[:20]) if s is not None]
                    if sizes:
                        median = sorted(sizes)[len(sizes) // 2]
                        wall_ratio = max(sizes) / median if median > 0 else 0.0
                except json.JSONDecodeError:
                    pass
            rng = curr_bar["high"] - curr_bar["low"]
            if wall_ratio >= WALL_RATIO_THRESHOLD and rng < (prev_bar["high"] - prev_bar["low"]) * 0.5:
                absorption = 70.0
            if wall_ratio >= WALL_RATIO_THRESHOLD * 1.5:
                absorption = max(absorption, 85.0)

            out = {
                "exchange": exchange,
                "symbol": symbol,
                "ts": curr_start,
                "exhaustion_score": round(exhaustion, 2),
                "absorption_score": round(absorption, 2),
            }
            payload = json.dumps(out)
            await r.xadd(STREAM_SCORES_EXHAUSTION, {"payload": payload}, maxlen=10000)
            await r.rpush(scores_key, payload)
            await r.ltrim(scores_key, -SCORES_MAXLEN, -1)
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[exhaustion] Error: {e}")
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379")
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()
    asyncio.run(run_exhaustion_engine(args.redis, args.exchange, args.symbol))


if __name__ == "__main__":
    main()
