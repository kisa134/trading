"""
Hot storage: reads from Redis Streams (orderbook_updates, trades), maintains in-memory
orderbook per instrument, writes DOM + ring buffers (slices, trades) to Redis.
"""
import asyncio
import json
import argparse
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import redis.asyncio as redis

from shared.schemas import EXCHANGE_FIELD, SYMBOL_FIELD, TYPE_FIELD, TS_FIELD, BIDS_FIELD, ASKS_FIELD
from shared.streams import (
    STREAM_ORDERBOOK_UPDATES,
    STREAM_TRADES,
    REDIS_KEY_DOM,
    REDIS_KEY_ORDERBOOK_SLICES,
    REDIS_KEY_TRADES,
    SLICES_MAXLEN,
    TRADES_MAXLEN,
)


def _apply_snapshot(bids: dict, asks: dict, payload: dict) -> None:
    bids.clear()
    asks.clear()
    for entry in payload.get(BIDS_FIELD, []):
        if len(entry) >= 2:
            p, s = float(entry[0]), float(entry[1])
            if s > 0:
                bids[p] = s
    for entry in payload.get(ASKS_FIELD, []):
        if len(entry) >= 2:
            p, s = float(entry[0]), float(entry[1])
            if s > 0:
                asks[p] = s


def _apply_delta(bids: dict, asks: dict, payload: dict) -> None:
    for entry in payload.get(BIDS_FIELD, []):
        if len(entry) >= 2:
            p, s = float(entry[0]), float(entry[1])
            if s <= 0:
                bids.pop(p, None)
            else:
                bids[p] = s
    for entry in payload.get(ASKS_FIELD, []):
        if len(entry) >= 2:
            p, s = float(entry[0]), float(entry[1])
            if s <= 0:
                asks.pop(p, None)
            else:
                asks[p] = s


def _to_lists(bids: dict, asks: dict, limit: int = 200):
    b = sorted(bids.items(), key=lambda x: -x[0])[:limit]
    a = sorted(asks.items(), key=lambda x: x[0])[:limit]
    return [[p, s] for p, s in b], [[p, s] for p, s in a]


async def run_hot_storage(redis_url: str):
    r = redis.from_url(redis_url, decode_responses=True)
    # in-memory orderbooks: (exchange, symbol) -> (bids dict, asks dict)
    orderbooks: dict[tuple[str, str], tuple[dict, dict]] = {}
    last_ids = {STREAM_ORDERBOOK_UPDATES: "$", STREAM_TRADES: "$"}

    while True:
        try:
            streams = [
                [STREAM_ORDERBOOK_UPDATES, last_ids[STREAM_ORDERBOOK_UPDATES]],
                [STREAM_TRADES, last_ids[STREAM_TRADES]],
            ]
            result = await r.xread(streams=dict(streams), count=100, block=5000)
            if not result:
                continue

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

                    if stream_name == STREAM_ORDERBOOK_UPDATES:
                        exchange = payload.get(EXCHANGE_FIELD, "")
                        symbol = payload.get(SYMBOL_FIELD, "")
                        key = (exchange, symbol)
                        if key not in orderbooks:
                            orderbooks[key] = ({}, {})
                        bids, asks = orderbooks[key]
                        if payload.get(TYPE_FIELD) == "snapshot":
                            _apply_snapshot(bids, asks, payload)
                        else:
                            _apply_delta(bids, asks, payload)
                        ts = payload.get(TS_FIELD, 0)
                        b_list, a_list = _to_lists(bids, asks)
                        dom_key = REDIS_KEY_DOM.format(exchange=exchange, symbol=symbol)
                        await r.set(dom_key, json.dumps({"ts": ts, "bids": b_list, "asks": a_list}))
                        slices_key = REDIS_KEY_ORDERBOOK_SLICES.format(exchange=exchange, symbol=symbol)
                        slice_item = json.dumps({"ts": ts, "bids": b_list, "asks": a_list})
                        await r.rpush(slices_key, slice_item)
                        await r.ltrim(slices_key, -SLICES_MAXLEN, -1)

                    elif stream_name == STREAM_TRADES:
                        exchange = payload.get(EXCHANGE_FIELD, "")
                        symbol = payload.get(SYMBOL_FIELD, "")
                        trades_key = REDIS_KEY_TRADES.format(exchange=exchange, symbol=symbol)
                        await r.rpush(trades_key, payload_str)
                        await r.ltrim(trades_key, -TRADES_MAXLEN, -1)

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[hot] Error: {e}")
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379", help="Redis URL")
    args = parser.parse_args()
    asyncio.run(run_hot_storage(args.redis))


if __name__ == "__main__":
    main()
