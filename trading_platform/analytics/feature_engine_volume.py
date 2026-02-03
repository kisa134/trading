"""
Feature engine: volume score (Score_volume) from trades stream.
Aggregates per bar and stores latest score in Redis.
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

from shared.streams import STREAM_TRADES, REDIS_KEY_SCORE_VOLUME

ROLLING_BARS = 50


def _zscore(values: deque, x: float) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / max(len(values), 1)
    std = var ** 0.5
    if std <= 1e-9:
        return 0.0
    return (x - mean) / std


def _score_from_z(z: float) -> float:
    if z <= 0.5:
        return 0.0
    if z <= 1.0:
        return 2.0
    if z <= 2.0:
        return 4.0
    return 6.0


async def run_feature_engine_volume(redis_url: str, bar_ms: int = 60000):
    r = redis.from_url(redis_url, decode_responses=True)
    last_id = "$"
    # per (exchange, symbol)
    state: dict[tuple[str, str], dict] = {}

    while True:
        try:
            result = await r.xread({STREAM_TRADES: last_id}, count=200, block=1000)
            if not result:
                continue
            for _stream, messages in result:
                for msg_id, fields in messages:
                    last_id = msg_id
                    payload_str = (fields or {}).get("payload")
                    if not payload_str:
                        continue
                    try:
                        t = json.loads(payload_str)
                    except json.JSONDecodeError:
                        continue
                    exchange = t.get("exchange", "")
                    symbol = t.get("symbol", "")
                    ts = int(t.get("ts", 0))
                    key = (exchange, symbol)
                    if key not in state:
                        state[key] = {
                            "bar_start": (ts // bar_ms) * bar_ms,
                            "buy": 0.0,
                            "sell": 0.0,
                            "total": 0.0,
                            "vol_hist": deque(maxlen=ROLLING_BARS),
                            "delta_hist": deque(maxlen=ROLLING_BARS),
                        }
                    st = state[key]
                    bar_start = (ts // bar_ms) * bar_ms
                    if bar_start != st["bar_start"]:
                        total = st["total"]
                        delta = st["buy"] - st["sell"]
                        z_vol = _zscore(st["vol_hist"], total)
                        z_delta = _zscore(st["delta_hist"], abs(delta))
                        score = max(_score_from_z(z_vol), _score_from_z(z_delta))
                        out = {
                            "exchange": exchange,
                            "symbol": symbol,
                            "ts": st["bar_start"],
                            "score_volume": round(score, 3),
                            "total": total,
                            "delta": delta,
                        }
                        await r.set(REDIS_KEY_SCORE_VOLUME.format(exchange=exchange, symbol=symbol), json.dumps(out), ex=300)
                        st["vol_hist"].append(total)
                        st["delta_hist"].append(abs(delta))
                        st["bar_start"] = bar_start
                        st["buy"] = 0.0
                        st["sell"] = 0.0
                        st["total"] = 0.0
                    size = float(t.get("size", t.get("volume", 0)))
                    side = (t.get("side") or "").lower()
                    st["total"] += size
                    if side in ("buy", "bid"):
                        st["buy"] += size
                    else:
                        st["sell"] += size
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[feature_volume] Error: {e}")
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379")
    parser.add_argument("--bar-ms", type=int, default=60000)
    args = parser.parse_args()
    asyncio.run(run_feature_engine_volume(args.redis, args.bar_ms))


if __name__ == "__main__":
    main()
