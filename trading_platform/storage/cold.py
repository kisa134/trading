"""
Cold storage writer: reads from Redis Streams (trades, orderbook_updates, heatmap_slices,
footprint_bars, events) and batches inserts into PostgreSQL/TimescaleDB.
Optional: set COLD_STORAGE_URL (e.g. postgresql://user:pass@localhost:5432/db) to enable.
"""
import asyncio
import json
import argparse
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import redis.asyncio as redis

from shared.streams import (
    STREAM_TRADES,
    STREAM_ORDERBOOK_UPDATES,
    STREAM_HEATMAP_SLICES,
    STREAM_FOOTPRINT_BARS,
    STREAM_EVENTS,
)

BATCH_SIZE = 100
BATCH_INTERVAL_SEC = 5.0


async def run_cold_writer(redis_url: str, cold_url: str):
    try:
        import asyncpg
    except ImportError:
        print("[cold] asyncpg not installed; cold storage disabled")
        return
    r = redis.from_url(redis_url, decode_responses=True)
    last_ids = {
        STREAM_TRADES: "$",
        STREAM_ORDERBOOK_UPDATES: "$",
        STREAM_HEATMAP_SLICES: "$",
        STREAM_FOOTPRINT_BARS: "$",
        STREAM_EVENTS: "$",
    }
    trades_batch = []
    snapshots_batch = []
    heatmap_batch = []
    footprint_batch = []
    events_batch = []

    async def flush(conn):
        nonlocal trades_batch, snapshots_batch, heatmap_batch, footprint_batch, events_batch
        if trades_batch:
            await conn.executemany(
                "INSERT INTO trades (exchange, symbol, side, price, size, ts, trade_id) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                trades_batch,
            )
            trades_batch = []
        if snapshots_batch:
            await conn.executemany(
                "INSERT INTO orderbook_snapshots (exchange, symbol, ts, bids, asks) VALUES ($1, $2, $3, $4::jsonb, $5::jsonb)",
                snapshots_batch,
            )
            snapshots_batch = []
        if heatmap_batch:
            await conn.executemany(
                "INSERT INTO heatmap_rows (exchange, symbol, ts, price_bin, volume_bid, volume_ask) VALUES ($1, $2, $3, $4, $5, $6)",
                heatmap_batch,
            )
            heatmap_batch = []
        if footprint_batch:
            await conn.executemany(
                "INSERT INTO footprint_bars (exchange, symbol, bar_start, bar_end, price, volume_bid, volume_ask, delta, poc_price, imbalance_levels) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)",
                footprint_batch,
            )
            footprint_batch = []
        if events_batch:
            await conn.executemany(
                "INSERT INTO events (type, exchange, symbol, price, side, volume, ts_start, ts_end, payload) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)",
                events_batch,
            )
            events_batch = []

    while True:
        try:
            conn = await asyncpg.connect(cold_url)
        except Exception as e:
            print(f"[cold] DB connect failed: {e}, retry in 10s")
            await asyncio.sleep(10)
            continue
        try:
            last_flush = asyncio.get_event_loop().time()
            while True:
                result = await r.xread(last_ids, count=200, block=1000)
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
                            if stream_name == STREAM_TRADES:
                                trades_batch.append((
                                    exchange,
                                    symbol,
                                    payload.get("side", ""),
                                    float(payload.get("price", 0)),
                                    float(payload.get("size", 0)),
                                    int(payload.get("ts", 0)),
                                    payload.get("trade_id"),
                                ))
                            elif stream_name == STREAM_ORDERBOOK_UPDATES and payload.get("type") == "snapshot":
                                snapshots_batch.append((
                                    exchange,
                                    symbol,
                                    int(payload.get("ts", 0)),
                                    json.dumps(payload.get("bids", [])),
                                    json.dumps(payload.get("asks", [])),
                                ))
                            elif stream_name == STREAM_HEATMAP_SLICES:
                                ts = int(payload.get("ts", 0))
                                for row in payload.get("rows", []):
                                    heatmap_batch.append((
                                        exchange,
                                        symbol,
                                        ts,
                                        float(row.get("price", 0)),
                                        float(row.get("vol_bid", 0)),
                                        float(row.get("vol_ask", 0)),
                                    ))
                            elif stream_name == STREAM_FOOTPRINT_BARS:
                                bar_start = int(payload.get("start", 0))
                                bar_end = int(payload.get("end", 0))
                                poc_price = payload.get("poc_price")
                                poc_price = float(poc_price) if poc_price is not None else None
                                imbalance_levels = payload.get("imbalance_levels")
                                imbalance_json = json.dumps(imbalance_levels) if imbalance_levels is not None else None
                                for level in payload.get("levels", []):
                                    footprint_batch.append((
                                        exchange,
                                        symbol,
                                        bar_start,
                                        bar_end,
                                        float(level.get("price", 0)),
                                        float(level.get("vol_bid", 0)),
                                        float(level.get("vol_ask", 0)),
                                        float(level.get("delta", 0)),
                                        poc_price,
                                        imbalance_json,
                                    ))
                            elif stream_name == STREAM_EVENTS:
                                ev = payload
                                ts_start = ev.get("ts_start") or ev.get("ts")
                                ts_end = ev.get("ts_end") or ev.get("ts")
                                price = ev.get("price")
                                side = ev.get("side")
                                vol = ev.get("size") or (ev.get("icebergs", [{}])[0].get("volume_estimate") if ev.get("icebergs") else None)
                                events_batch.append((
                                    ev.get("type", ""),
                                    exchange,
                                    symbol,
                                    price,
                                    side,
                                    vol,
                                    ts_start,
                                    ts_end,
                                    json.dumps(ev),
                                ))

                now = asyncio.get_event_loop().time()
                if now - last_flush >= BATCH_INTERVAL_SEC or (
                    len(trades_batch) + len(snapshots_batch) + len(heatmap_batch) + len(footprint_batch) + len(events_batch)
                ) >= BATCH_SIZE:
                    await flush(conn)
                    last_flush = now
        except asyncio.CancelledError:
            await flush(conn)
            break
        except Exception as e:
            print(f"[cold] Error: {e}")
            await asyncio.sleep(5)
        finally:
            await conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379")
    parser.add_argument("--cold", default=os.environ.get("COLD_STORAGE_URL", ""), help="PostgreSQL URL for cold storage")
    args = parser.parse_args()
    if not args.cold:
        print("[cold] COLD_STORAGE_URL not set; idling (set env to enable)")
        while True:
            time.sleep(3600)
        return
    asyncio.run(run_cold_writer(args.redis, args.cold))


if __name__ == "__main__":
    main()
