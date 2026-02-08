"""
Graph writer worker: reads from Redis Streams (events, liquidations, open_interest),
writes Event and MarketState nodes to Neo4j. No-op if NEO4J_URI not set.
"""
import asyncio
import json
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import redis.asyncio as redis

from shared.streams import (
    STREAM_EVENTS,
    STREAM_LIQUIDATIONS,
    STREAM_OPEN_INTEREST,
    REDIS_KEY_TRADES,
)


async def get_last_price(r: redis.Redis, exchange: str, symbol: str) -> float | None:
    """Read last trade price from Redis list."""
    key = REDIS_KEY_TRADES.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -1, -1)
    if not items:
        return None
    try:
        t = json.loads(items[0])
        return float(t.get("price", 0)) if t.get("price") else None
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


async def run_graph_writer(redis_url: str):
    r = redis.from_url(redis_url, decode_responses=True)
    last_ids = {
        STREAM_EVENTS: "$",
        STREAM_LIQUIDATIONS: "$",
        STREAM_OPEN_INTEREST: "$",
    }
    # (exchange, symbol) -> (ts, oi) for MarketState
    last_oi: dict[tuple[str, str], tuple[int, float]] = {}
    market_state_interval = 5.0
    last_market_state_flush = 0.0

    from services.graph.writer import write_event, write_market_state

    while True:
        try:
            streams = [[name, last_ids[name]] for name in last_ids]
            result = await r.xread(streams=dict(streams), count=100, block=2000)
            if result:
                for stream_name, messages in result:
                    for msg_id, fields in messages:
                        last_ids[stream_name] = msg_id
                        payload_str = (fields or {}).get("payload")
                        if not payload_str:
                            continue
                        try:
                            payload = json.loads(payload_str)
                        except json.JSONDecodeError:
                            continue
                        exchange = payload.get("exchange", "")
                        symbol = payload.get("symbol", "")
                        if not exchange or not symbol:
                            continue

                        if stream_name == STREAM_EVENTS:
                            event_type = payload.get("type", "event")
                            ts = int(payload.get("ts_start") or payload.get("ts") or 0)
                            write_event(exchange, symbol, event_type, ts, payload)
                            price = await get_last_price(r, exchange, symbol)
                            oi_data = last_oi.get((exchange, symbol))
                            oi = oi_data[1] if oi_data else None
                            write_market_state(exchange, symbol, ts, price or 0.0, oi)

                        elif stream_name == STREAM_LIQUIDATIONS:
                            ts = int(payload.get("ts", 0))
                            liq_payload = {
                                "price": payload.get("price"),
                                "quantity": payload.get("quantity"),
                                "side": payload.get("side"),
                            }
                            write_event(exchange, symbol, "liquidation", ts, liq_payload)
                            price = float(payload.get("price", 0)) or (await get_last_price(r, exchange, symbol))
                            oi_data = last_oi.get((exchange, symbol))
                            oi = oi_data[1] if oi_data else None
                            write_market_state(exchange, symbol, ts, price or 0.0, oi)

                        elif stream_name == STREAM_OPEN_INTEREST:
                            ts = int(payload.get("ts", 0))
                            oi = float(payload.get("open_interest", 0) or 0)
                            last_oi[(exchange, symbol)] = (ts, oi)

            # Periodic MarketState flush for pairs we have OI for (price from trades)
            now = time.time()
            if now - last_market_state_flush >= market_state_interval and last_oi:
                for (exchange, symbol), (ts, oi) in list(last_oi.items()):
                    price = await get_last_price(r, exchange, symbol)
                    if price is not None:
                        write_market_state(exchange, symbol, ts, price, oi)
                last_market_state_flush = now

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[graph_writer] Error: {e}")
            await asyncio.sleep(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default=os.environ.get("REDIS_URL", "redis://localhost:6379"))
    args = parser.parse_args()
    asyncio.run(run_graph_writer(args.redis))


if __name__ == "__main__":
    main()
