"""
Trend score engine: combines Score_candle, Score_volume, Score_orderbook into Score_impulse,
TrendPower, and TrendPower delta. Publishes to stream and Redis list.
"""
import asyncio
import json
import argparse
import time
import sys
import os
from collections import deque

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import redis.asyncio as redis

from shared.streams import (
    STREAM_SCORES_TREND,
    REDIS_KEY_SCORE_CANDLE,
    REDIS_KEY_SCORE_VOLUME,
    REDIS_KEY_SCORE_ORDERBOOK,
    REDIS_KEY_SCORES_TREND,
    SCORES_MAXLEN,
)


async def run_trend_score_engine(redis_url: str, exchange: str, symbol: str, n_window: int, w1: float, w2: float, w3: float):
    r = redis.from_url(redis_url, decode_responses=True)
    key_candle = REDIS_KEY_SCORE_CANDLE.format(exchange=exchange, symbol=symbol)
    key_volume = REDIS_KEY_SCORE_VOLUME.format(exchange=exchange, symbol=symbol)
    key_orderbook = REDIS_KEY_SCORE_ORDERBOOK.format(exchange=exchange, symbol=symbol)
    key_scores = REDIS_KEY_SCORES_TREND.format(exchange=exchange, symbol=symbol)
    history = deque(maxlen=n_window)
    last_power = 0.0

    while True:
        try:
            raw_candle, raw_volume, raw_orderbook = await r.mget([key_candle, key_volume, key_orderbook])
            if not raw_candle or not raw_volume or not raw_orderbook:
                await asyncio.sleep(0.5)
                continue
            try:
                candle = json.loads(raw_candle)
                volume = json.loads(raw_volume)
                orderbook = json.loads(raw_orderbook)
            except json.JSONDecodeError:
                await asyncio.sleep(0.5)
                continue
            score_candle = float(candle.get("score_candle", 0))
            score_volume = float(volume.get("score_volume", 0))
            score_orderbook = float(orderbook.get("score_orderbook", 0))
            direction = int(candle.get("dir", 0))
            total = w1 * score_candle + w2 * score_volume + w3 * score_orderbook
            max_total = (w1 + w2 + w3) * 6.0 or 1.0
            score_impulse = (total / max_total) * 100.0 * direction
            ts = max(int(candle.get("ts", 0)), int(volume.get("ts", 0)), int(orderbook.get("ts", 0)), int(time.time() * 1000))
            history.append(score_impulse)
            trend_power = sum(history)
            trend_delta = trend_power - last_power
            last_power = trend_power
            out = {
                "exchange": exchange,
                "symbol": symbol,
                "ts": ts,
                "score_candle": round(score_candle, 3),
                "score_volume": round(score_volume, 3),
                "score_orderbook": round(score_orderbook, 3),
                "score_impulse": round(score_impulse, 3),
                "trend_power": round(trend_power, 3),
                "trend_power_delta": round(trend_delta, 3),
            }
            payload = json.dumps(out)
            await r.xadd(STREAM_SCORES_TREND, {"payload": payload}, maxlen=10000)
            await r.rpush(key_scores, payload)
            await r.ltrim(key_scores, -SCORES_MAXLEN, -1)
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[trend_score] Error: {e}")
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379")
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--window", type=int, default=50)
    parser.add_argument("--w1", type=float, default=1.0)
    parser.add_argument("--w2", type=float, default=1.0)
    parser.add_argument("--w3", type=float, default=1.0)
    args = parser.parse_args()
    asyncio.run(run_trend_score_engine(args.redis, args.exchange, args.symbol, args.window, args.w1, args.w2, args.w3))


if __name__ == "__main__":
    main()
