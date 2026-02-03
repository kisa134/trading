"""
Tape aggregator: reads trades stream, aggregates buy/sell/delta by windows (1s/5s/1m),
large trades, level clusters; writes to Redis.
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

from shared.streams import STREAM_TRADES, REDIS_KEY_TAPE

WINDOWS = {"1s": 1000, "5s": 5000, "1m": 60000}
LARGE_TRADE_MULT = 3.0
MAX_RECENT_TRADES = 500


async def run_tape_aggregator(redis_url: str, exchange_filter: str = "", symbol_filter: str = ""):
    r = redis.from_url(redis_url, decode_responses=True)
    last_id = "$"
    # per (exchange, symbol): deque of (ts, side, price, size)
    recent: dict[tuple[str, str], deque] = {}

    while True:
        try:
            result = await r.xread({STREAM_TRADES: last_id}, count=100, block=1000)
            if not result:
                continue
            for stream_name, messages in result:
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
                        recent[key] = deque(maxlen=MAX_RECENT_TRADES)
                    side = t.get("side", "")
                    price = float(t.get("price", 0))
                    size = float(t.get("size", 0))
                    ts = int(t.get("ts", 0))
                    recent[key].append({"ts": ts, "side": side, "price": price, "size": size})

                    # Aggregate by windows
                    now = ts
                    agg = {}
                    for label, window_ms in WINDOWS.items():
                        buy_vol = sell_vol = 0.0
                        for x in recent[key]:
                            if now - x["ts"] > window_ms:
                                continue
                            if (x["side"] or "").lower() in ("buy", "bid"):
                                buy_vol += x["size"]
                            else:
                                sell_vol += x["size"]
                        agg[label] = {"buy_vol": buy_vol, "sell_vol": sell_vol, "delta": buy_vol - sell_vol}

                    # Large trades: vs rolling avg
                    vol_list = [x["size"] for x in list(recent[key])[-100:]]
                    avg_vol = sum(vol_list) / len(vol_list) if vol_list else size
                    large = size >= avg_vol * LARGE_TRADE_MULT if avg_vol > 0 else False

                    tape_key = REDIS_KEY_TAPE.format(exchange=exchange, symbol=symbol)
                    out = {"ts": now, "aggregates": agg, "last_trade": {"price": price, "size": size, "side": side, "large": large}}
                    await r.set(tape_key, json.dumps(out), ex=60)

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[tape] Error: {e}")
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379")
    parser.add_argument("--exchange", default="", help="Filter by exchange")
    parser.add_argument("--symbol", default="", help="Filter by symbol")
    args = parser.parse_args()
    asyncio.run(run_tape_aggregator(args.redis, args.exchange, args.symbol))


if __name__ == "__main__":
    main()
