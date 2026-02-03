"""
Feature engine: candle score (Score_candle) from kline stream.
Produces latest candle score in Redis for trend engine.
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

from shared.streams import STREAM_KLINE, REDIS_KEY_SCORE_CANDLE

RANGE_WINDOW = 50


def _score_candle(o: float, h: float, lo: float, c: float, avg_range: float) -> tuple[float, int]:
    rng = max(h - lo, 1e-9)
    body = abs(c - o)
    body_ratio = body / rng
    range_factor = rng / max(avg_range, 1e-9)
    raw = (range_factor - 0.5) / 1.5 * 6.0
    score = max(0.0, min(6.0, raw))
    score *= 0.5 + 0.5 * body_ratio
    score = max(0.0, min(6.0, score))
    direction = 1 if c > o else (-1 if c < o else 0)
    return round(score, 3), direction


async def run_feature_engine_candles(redis_url: str):
    r = redis.from_url(redis_url, decode_responses=True)
    last_id = "$"
    ranges: dict[tuple[str, str], deque] = {}

    while True:
        try:
            result = await r.xread({STREAM_KLINE: last_id}, count=200, block=1000)
            if not result:
                continue
            for _stream, messages in result:
                for msg_id, fields in messages:
                    last_id = msg_id
                    payload_str = (fields or {}).get("payload")
                    if not payload_str:
                        continue
                    try:
                        k = json.loads(payload_str)
                    except json.JSONDecodeError:
                        continue
                    if not k.get("confirm", False):
                        continue
                    exchange = k.get("exchange", "")
                    symbol = k.get("symbol", "")
                    key = (exchange, symbol)
                    if key not in ranges:
                        ranges[key] = deque(maxlen=RANGE_WINDOW)
                    o = float(k.get("open", 0))
                    h = float(k.get("high", 0))
                    lo = float(k.get("low", 0))
                    c = float(k.get("close", 0))
                    rng = max(h - lo, 0.0)
                    ranges[key].append(rng)
                    avg_range = (sum(ranges[key]) / len(ranges[key])) if ranges[key] else rng
                    score, direction = _score_candle(o, h, lo, c, avg_range)
                    ts = int(k.get("start", time.time() * 1000))
                    out = {
                        "exchange": exchange,
                        "symbol": symbol,
                        "ts": ts,
                        "score_candle": score,
                        "dir": direction,
                    }
                    await r.set(REDIS_KEY_SCORE_CANDLE.format(exchange=exchange, symbol=symbol), json.dumps(out), ex=300)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[feature_candle] Error: {e}")
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379")
    args = parser.parse_args()
    asyncio.run(run_feature_engine_candles(args.redis))


if __name__ == "__main__":
    main()
