"""
Tick anomaly detector: consumes trades from Redis (stream or list), emits volume/delta anomalies.
Placeholder for Visual Mamba (SSM) when GPU available; uses rule-based heuristics for v1.
Writes to STREAM_AI_MAMBA_ANOMALIES and REDIS_KEY_AI_ANOMALIES for AI Controller.
"""
import asyncio
import json
import argparse
import sys
import os
from collections import deque

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import redis.asyncio as redis

from shared.streams import (
    STREAM_TRADES,
    STREAM_AI_MAMBA_ANOMALIES,
    REDIS_KEY_AI_ANOMALIES,
)


ROLLING_WINDOW = 100
VOLUME_SPIKE_MULT = 2.5
ANOMALY_TTL_SEC = 60


async def run_tick_anomaly_worker(redis_url: str, exchange_filter: str = "", symbol_filter: str = ""):
    r = redis.from_url(redis_url, decode_responses=True)
    last_id = "$"
    recent: dict[tuple[str, str], deque] = {}

    while True:
        try:
            result = await r.xread({STREAM_TRADES: last_id}, count=50, block=1000)
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
                    if exchange_filter and exchange != exchange_filter:
                        continue
                    if symbol_filter and symbol != symbol_filter:
                        continue
                    key = (exchange, symbol)
                    if key not in recent:
                        recent[key] = deque(maxlen=ROLLING_WINDOW)
                    side = (t.get("side") or "").lower()
                    price = float(t.get("price", 0))
                    size = float(t.get("size", t.get("volume", 0)))
                    ts = int(t.get("ts", 0))
                    recent[key].append({"ts": ts, "side": side, "price": price, "size": size})

                    vol_list = [x["size"] for x in recent[key]]
                    avg_vol = sum(vol_list) / len(vol_list) if vol_list else size
                    if avg_vol <= 0:
                        continue
                    if size >= avg_vol * VOLUME_SPIKE_MULT:
                        anomaly = {
                            "exchange": exchange,
                            "symbol": symbol,
                            "ts": ts,
                            "type": "volume_spike",
                            "price": price,
                            "size": size,
                            "side": side,
                            "avg_vol": round(avg_vol, 4),
                            "ratio": round(size / avg_vol, 2),
                        }
                        await r.xadd(
                            STREAM_AI_MAMBA_ANOMALIES,
                            {"payload": json.dumps(anomaly)},
                            maxlen=5000,
                        )
                        anomalies_key = REDIS_KEY_AI_ANOMALIES.format(exchange=exchange, symbol=symbol)
                        await r.set(anomalies_key, json.dumps(anomaly), ex=ANOMALY_TTL_SEC)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[tick_anomaly] {e}")
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379")
    parser.add_argument("--exchange", default="", help="Filter by exchange")
    parser.add_argument("--symbol", default="", help="Filter by symbol")
    args = parser.parse_args()
    asyncio.run(run_tick_anomaly_worker(args.redis, args.exchange, args.symbol))


if __name__ == "__main__":
    main()
