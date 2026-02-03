"""
OKX ingestor: REST snapshot at start, then WebSocket stream.
Normalizes orderbook/trades to shared format and publishes to Redis Streams.
InstId format: BTC-USDT (OKX uses dash).
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

OKX_WS_URL = "wss://ws.okx.com:8443/ws/v5/public"
OKX_REST_BOOKS = "https://www.okx.com/api/v5/market/books"
EXCHANGE = "okx"
DEPTH_SZ = 200


def _symbol_to_inst_id(symbol: str) -> str:
    if "-" in symbol:
        return symbol
    if symbol.endswith("USDT"):
        return symbol[:-4] + "-USDT"
    return symbol


def _inst_id_to_symbol(inst_id: str) -> str:
    return inst_id.replace("-", "")


def _parse_bids_asks(b: list, a: list):
    # OKX: [[price, size, num_orders], ...] or [[price, size], ...]
    bids = [[float(x[0]), float(x[1])] for x in (b or []) if len(x) >= 2]
    asks = [[float(x[0]), float(x[1])] for x in (a or []) if len(x) >= 2]
    return bids, asks


async def fetch_orderbook_snapshot(inst_id: str, sz: int = DEPTH_SZ) -> dict | None:
    import aiohttp
    params = {"instId": inst_id, "sz": sz}
    async with aiohttp.ClientSession() as session:
        async with session.get(OKX_REST_BOOKS, params=params) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
    if data.get("code") != "0":
        return None
    r = data.get("data", [{}])
    if not r:
        return None
    r = r[0]
    ts = int(r.get("ts", time.time() * 1000))
    bids, asks = _parse_bids_asks(r.get("bids", []), r.get("asks", []))
    symbol = _inst_id_to_symbol(inst_id)
    return {
        "exchange": EXCHANGE,
        "symbol": symbol,
        "type": "snapshot",
        "ts": ts,
        "bids": bids,
        "asks": asks,
        "update_id": r.get("ts"),
    }


async def run_ingestor(redis_url: str, symbol: str):
    r = redis.from_url(redis_url, decode_responses=True)
    inst_id = _symbol_to_inst_id(symbol)
    subscribe_msg = json.dumps({
        "op": "subscribe",
        "args": [
            {"channel": "books", "instId": inst_id},
            {"channel": "trades", "instId": inst_id},
        ],
    })

    snap = await fetch_orderbook_snapshot(inst_id)
    if snap:
        await r.xadd(STREAM_ORDERBOOK_UPDATES, {"payload": json.dumps(snap)}, maxlen=10000)
        print(f"[okx] Published initial snapshot for {symbol}")

    async for ws in websockets.connect(OKX_WS_URL, ping_interval=25, ping_timeout=25, close_timeout=5):
        try:
            await ws.send(subscribe_msg)
            async for raw in ws:
                data = json.loads(raw)
                if "event" in data:
                    continue
                arg = data.get("arg", {})
                channel = arg.get("channel", "")
                payload_inst = arg.get("instId", "")
                if channel == "books":
                    for d in data.get("data", []):
                        ts = int(d.get("ts", time.time() * 1000))
                        bids, asks = _parse_bids_asks(d.get("bids", []), d.get("asks", []))
                        ev = orderbook_event(
                            EXCHANGE,
                            _inst_id_to_symbol(payload_inst),
                            "snapshot" if d.get("action") == "snapshot" else "delta",
                            ts,
                            bids,
                            asks,
                            d.get("ts"),
                        )
                        await r.xadd(STREAM_ORDERBOOK_UPDATES, {"payload": json.dumps(ev)}, maxlen=10000)
                elif channel == "trades":
                    for t in data.get("data", []):
                        price = float(t.get("fillPx", t.get("px", 0)))
                        size = float(t.get("fillSz", t.get("sz", 0)))
                        side = "Buy" if t.get("side") == "buy" else "Sell"
                        ts = int(t.get("ts", 0))
                        trade_id = t.get("tradeId", "")
                        if size <= 0:
                            continue
                        ev = trade_event(EXCHANGE, _inst_id_to_symbol(payload_inst), side, price, size, ts, trade_id)
                        await r.xadd(STREAM_TRADES, {"payload": json.dumps(ev)}, maxlen=50000)
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[okx] WS closed: {e}, reconnecting...")
        except Exception as e:
            print(f"[okx] Error: {e}, reconnecting...")
        await asyncio.sleep(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()
    asyncio.run(run_ingestor(args.redis, args.symbol))


if __name__ == "__main__":
    main()
