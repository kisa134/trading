"""
Bybit ingestor: REST snapshot at start, then WebSocket stream.
Normalizes orderbook/trades/kline to shared format and publishes to Redis Streams.
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

from shared.schemas import orderbook_event, trade_event, candle_event, open_interest_event, liquidation_event
from shared.streams import (
    STREAM_ORDERBOOK_UPDATES,
    STREAM_TRADES,
    STREAM_KLINE,
    STREAM_OPEN_INTEREST,
    STREAM_LIQUIDATIONS,
)

BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/linear"
BYBIT_REST_ORDERBOOK = "https://api.bybit.com/v5/market/orderbook"
EXCHANGE = "bybit"
ORDERBOOK_DEPTH = 200
KLINE_INTERVAL = 1


def _parse_bids_asks(b: list, a: list):
    """Parse Bybit format [[price, size], ...] to our format."""
    bids = [[float(x[0]), float(x[1])] for x in (b or []) if len(x) >= 2]
    asks = [[float(x[0]), float(x[1])] for x in (a or []) if len(x) >= 2]
    return bids, asks


async def fetch_orderbook_snapshot(symbol: str, limit: int = ORDERBOOK_DEPTH) -> dict | None:
    """Fetch initial orderbook snapshot via REST."""
    import aiohttp
    params = {"category": "linear", "symbol": symbol, "limit": limit}
    async with aiohttp.ClientSession() as session:
        async with session.get(BYBIT_REST_ORDERBOOK, params=params) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
    if data.get("retCode") != 0:
        return None
    r = data.get("result", {})
    ts = int(r.get("ts", time.time() * 1000))
    bids, asks = _parse_bids_asks(r.get("b", []), r.get("a", []))
    return {
        "exchange": EXCHANGE,
        "symbol": symbol,
        "type": "snapshot",
        "ts": ts,
        "bids": bids,
        "asks": asks,
        "update_id": r.get("u"),
    }


async def run_ingestor(redis_url: str, symbol: str):
    r = redis.from_url(redis_url, decode_responses=True)
    trade_topic = f"publicTrade.{symbol}"
    book_topic = f"orderbook.{ORDERBOOK_DEPTH}.{symbol}"
    kline_topic = f"kline.{KLINE_INTERVAL}.{symbol}"
    tickers_topic = f"tickers.{symbol}"
    liquidation_topic = f"allLiquidation.{symbol}"
    subscribe_msg = json.dumps({
        "op": "subscribe",
        "args": [trade_topic, book_topic, kline_topic, tickers_topic, liquidation_topic],
    })

    # Initial snapshot
    snap = await fetch_orderbook_snapshot(symbol)
    if snap:
        await r.xadd(STREAM_ORDERBOOK_UPDATES, {"payload": json.dumps(snap)}, maxlen=10000)
        print(f"[bybit] Published initial snapshot for {symbol}")

    async for ws in websockets.connect(
        BYBIT_WS_URL,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=5,
    ):
        try:
            await ws.send(subscribe_msg)
            async for raw in ws:
                data = json.loads(raw)
                topic = data.get("topic")
                if not topic:
                    continue

                if topic == trade_topic:
                    for t in data.get("data", []):
                        price = float(t.get("p", 0))
                        vol = float(t.get("v", 0))
                        side = str(t.get("S", "Buy")).lower()
                        if side == "buy":
                            side = "Buy"
                        else:
                            side = "Sell"
                        ts = int(t.get("T", 0))
                        trade_id = t.get("i")
                        if vol <= 0:
                            continue
                        ev = trade_event(EXCHANGE, symbol, side, price, vol, ts, trade_id)
                        await r.xadd(STREAM_TRADES, {"payload": json.dumps(ev)}, maxlen=50000)

                elif topic == book_topic:
                    msg_type = data.get("type", "delta")
                    d = data.get("data", data)
                    ts = int(time.time() * 1000)
                    bids, asks = _parse_bids_asks(d.get("b", []), d.get("a", []))
                    ev = orderbook_event(
                        EXCHANGE,
                        symbol,
                        "snapshot" if msg_type == "snapshot" else "delta",
                        ts,
                        bids,
                        asks,
                        d.get("u"),
                    )
                    await r.xadd(STREAM_ORDERBOOK_UPDATES, {"payload": json.dumps(ev)}, maxlen=10000)

                elif topic == kline_topic:
                    for k in data.get("data", []):
                        start_ts = int(k.get("start", 0))
                        o = float(k.get("open", 0))
                        h = float(k.get("high", 0))
                        lo = float(k.get("low", 0))
                        c = float(k.get("close", 0))
                        vol = float(k.get("volume", 0))
                        confirm = bool(k.get("confirm", False))
                        ev = candle_event(EXCHANGE, symbol, str(KLINE_INTERVAL), start_ts, o, h, lo, c, vol, confirm)
                        await r.xadd(STREAM_KLINE, {"payload": json.dumps(ev)}, maxlen=5000)

                elif topic == tickers_topic:
                    for d in data.get("data", []):
                        ts = int(d.get("timestamp", time.time() * 1000))
                        oi = float(d.get("openInterest", 0) or 0)
                        oi_value = d.get("openInterestValue")
                        oi_val = float(oi_value) if oi_value is not None else None
                        ev = open_interest_event(EXCHANGE, symbol, ts, oi, oi_val)
                        await r.xadd(STREAM_OPEN_INTEREST, {"payload": json.dumps(ev)}, maxlen=5000)

                elif topic == liquidation_topic:
                    for liq in data.get("data", []):
                        ts = int(liq.get("updatedTime", time.time() * 1000))
                        price = float(liq.get("price", 0))
                        qty = float(liq.get("size", 0) or liq.get("qty", 0))
                        side = str(liq.get("side", "Buy")).strip()
                        if side.upper() == "BUY":
                            side = "Buy"
                        else:
                            side = "Sell"
                        ev = liquidation_event(EXCHANGE, symbol, ts, price, qty, side)
                        await r.xadd(STREAM_LIQUIDATIONS, {"payload": json.dumps(ev)}, maxlen=10000)

        except websockets.exceptions.ConnectionClosed as e:
            print(f"[bybit] WS closed: {e}, reconnecting...")
        except Exception as e:
            print(f"[bybit] Error: {e}, reconnecting...")
        await asyncio.sleep(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379", help="Redis URL")
    parser.add_argument("--symbol", default="BTCUSDT", help="Bybit symbol")
    args = parser.parse_args()
    asyncio.run(run_ingestor(args.redis, args.symbol))


if __name__ == "__main__":
    main()
