"""
Binance Futures ingestor: REST snapshot at start, then WebSocket stream.
Normalizes orderbook/trades to shared format and publishes to Redis Streams.
"""
import asyncio
import json
import argparse
import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import redis.asyncio as redis
import websockets

from shared.schemas import orderbook_event, trade_event
from shared.streams import STREAM_ORDERBOOK_UPDATES, STREAM_TRADES

BINANCE_WS_URL = "wss://fstream.binance.com/stream"
BINANCE_REST_DEPTH = "https://fapi.binance.com/fapi/v1/depth"
EXCHANGE = "binance"
ORDERBOOK_LIMIT = 200


def _parse_bids_asks(b: list, a: list):
    bids = [[float(x[0]), float(x[1])] for x in (b or []) if len(x) >= 2]
    asks = [[float(x[0]), float(x[1])] for x in (a or []) if len(x) >= 2]
    return bids, asks


async def fetch_orderbook_snapshot(symbol: str, limit: int = ORDERBOOK_LIMIT) -> dict | None:
    import aiohttp
    params = {"symbol": symbol, "limit": limit}
    async with aiohttp.ClientSession() as session:
        async with session.get(BINANCE_REST_DEPTH, params=params) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
    if "bids" not in data:
        return None
    ts = int(time.time() * 1000)
    bids, asks = _parse_bids_asks(data.get("bids", []), data.get("asks", []))
    return {
        "exchange": EXCHANGE,
        "symbol": symbol,
        "type": "snapshot",
        "ts": ts,
        "bids": bids,
        "asks": asks,
        "update_id": data.get("lastUpdateId"),
    }


async def run_ingestor(redis_url: str, symbol: str):
    r = redis.from_url(redis_url, decode_responses=True)
    sym_lower = symbol.lower()
    streams = [f"{sym_lower}@depth@100ms", f"{sym_lower}@aggTrade"]
    ws_url = f"{BINANCE_WS_URL}?streams={'/'.join(streams)}"

    snap = await fetch_orderbook_snapshot(symbol)
    if snap:
        await r.xadd(STREAM_ORDERBOOK_UPDATES, {"payload": json.dumps(snap)}, maxlen=10000)
        print(f"[binance] Published initial snapshot for {symbol}")

    async for ws in websockets.connect(ws_url, ping_interval=20, ping_timeout=20, close_timeout=5):
        try:
            async for raw in ws:
                data = json.loads(raw)
                stream = data.get("stream", "")
                payload = data.get("data", data)
                if f"{sym_lower}@depth" in stream:
                    ts = int(payload.get("E", time.time() * 1000))
                    bids, asks = _parse_bids_asks(payload.get("b", []), payload.get("a", []))
                    ev = orderbook_event(EXCHANGE, symbol, "delta", ts, bids, asks, payload.get("u"))
                    await r.xadd(STREAM_ORDERBOOK_UPDATES, {"payload": json.dumps(ev)}, maxlen=10000)
                elif f"{sym_lower}@aggTrade" in stream:
                    price = float(payload.get("p", 0))
                    size = float(payload.get("q", 0))
                    side = "Buy" if payload.get("m") is False else "Sell"
                    ts = int(payload.get("T", 0))
                    trade_id = str(payload.get("a", ""))
                    if size <= 0:
                        continue
                    ev = trade_event(EXCHANGE, symbol, side, price, size, ts, trade_id)
                    await r.xadd(STREAM_TRADES, {"payload": json.dumps(ev)}, maxlen=50000)
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[binance] WS closed: {e}, reconnecting...")
        except Exception as e:
            print(f"[binance] Error: {e}, reconnecting...")
        await asyncio.sleep(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()
    asyncio.run(run_ingestor(args.redis, args.symbol))


if __name__ == "__main__":
    main()
