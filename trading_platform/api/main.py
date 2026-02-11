"""
API: WebSocket channels orderbook_realtime, trades_realtime.
Reads from Redis (DOM, trades list) and optionally from Redis Streams for live push.
"""
import asyncio
import json
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import redis.asyncio as redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware

from shared.streams import (
    STREAM_ORDERBOOK_UPDATES,
    STREAM_TRADES,
    STREAM_KLINE,
    STREAM_OPEN_INTEREST,
    STREAM_LIQUIDATIONS,
    REDIS_KEY_DOM,
    REDIS_KEY_TRADES,
    REDIS_KEY_OI,
    REDIS_KEY_LIQUIDATIONS,
)

app = FastAPI(title="Trading Platform API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
COLD_STORAGE_URL = os.environ.get("COLD_STORAGE_URL", "")
redis_client: redis.Redis | None = None
# Subscribed clients: (exchange, symbol) -> set of (channel, websocket)
subscribers: dict[tuple[str, str], set[tuple[str, WebSocket]]] = {}
subscribers_lock = asyncio.Lock()


async def get_redis() -> redis.Redis:
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client


_broadcast_task: asyncio.Task | None = None


@app.on_event("startup")
async def startup():
    global _broadcast_task
    await get_redis()
    _broadcast_task = asyncio.create_task(broadcast_worker())


@app.on_event("shutdown")
async def shutdown():
    global redis_client, _broadcast_task
    if _broadcast_task:
        _broadcast_task.cancel()
        try:
            await _broadcast_task
        except asyncio.CancelledError:
            pass
    if redis_client:
        await redis_client.aclose()
        redis_client = None


def _match(exchange: str, symbol: str, payload: dict) -> bool:
    return payload.get("exchange") == exchange and payload.get("symbol") == symbol


STREAM_TO_CHANNEL = {
    STREAM_ORDERBOOK_UPDATES: "orderbook_realtime",
    STREAM_TRADES: "trades_realtime",
    STREAM_KLINE: "kline",
    STREAM_OPEN_INTEREST: "open_interest",
    STREAM_LIQUIDATIONS: "liquidations",
}


async def broadcast_worker():
    """Read from Redis Streams and push to subscribed WebSocket clients."""
    r = await get_redis()
    last_ids = {
        STREAM_ORDERBOOK_UPDATES: "$",
        STREAM_TRADES: "$",
        STREAM_KLINE: "$",
        STREAM_OPEN_INTEREST: "$",
        STREAM_LIQUIDATIONS: "$",
    }
    while True:
        try:
            result = await r.xread(
                last_ids,
                count=50,
                block=200,
            )
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
                    exchange = payload.get("exchange", "")
                    symbol = payload.get("symbol", "")
                    key = (exchange, symbol)
                    ch_expected = STREAM_TO_CHANNEL.get(stream_name)
                    async with subscribers_lock:
                        targets = list(subscribers.get(key, []))
                    msg = {"stream": stream_name, "data": payload}
                    text = json.dumps(msg)
                    dead = []
                    for ch, ws in targets:
                        if ch_expected and ch != ch_expected:
                            continue
                        try:
                            await ws.send_text(text)
                        except Exception:
                            dead.append((ch, ws))
                    for t in dead:
                        async with subscribers_lock:
                            s = subscribers.get(key, set())
                            s.discard(t)
                            if not s:
                                subscribers.pop(key, None)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(0.5)


@app.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    exchange: str = Query("bybit"),
    symbol: str = Query("BTCUSDT"),
    channels: str = Query("orderbook_realtime,trades_realtime"),
):
    await ws.accept()
    r = await get_redis()
    chan_list = [c.strip() for c in channels.split(",") if c.strip()]
    key = (exchange, symbol)
    async with subscribers_lock:
        if key not in subscribers:
            subscribers[key] = set()
        for ch in chan_list:
            subscribers[key].add((ch, ws))

    try:
        if "orderbook_realtime" in chan_list:
            dom_key = REDIS_KEY_DOM.format(exchange=exchange, symbol=symbol)
            dom_raw = await r.get(dom_key)
            if dom_raw:
                await ws.send_text(json.dumps({"type": "dom", "data": json.loads(dom_raw)}))

        while True:
            try:
                _ = await ws.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        async with subscribers_lock:
            s = subscribers.get(key, set())
            for ch in chan_list:
                s.discard((ch, ws))
            if not s:
                subscribers.pop(key, None)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/dom/{exchange}/{symbol}")
async def get_dom(exchange: str, symbol: str):
    """REST: current DOM snapshot."""
    r = await get_redis()
    key = REDIS_KEY_DOM.format(exchange=exchange, symbol=symbol)
    raw = await r.get(key)
    if not raw:
        return {"bids": [], "asks": [], "ts": 0}
    return json.loads(raw)


@app.get("/trades/{exchange}/{symbol}")
async def get_trades(exchange: str, symbol: str, limit: int = 100):
    """REST: last N trades from Redis list."""
    r = await get_redis()
    key = REDIS_KEY_TRADES.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -limit, -1)
    return [json.loads(x) for x in (items or [])]


@app.get("/kline/{exchange}/{symbol}")
async def get_kline(
    exchange: str,
    symbol: str,
    interval: int = Query(1, description="Candle interval in minutes"),
    limit: int = Query(500, le=2000),
):
    """REST: last N candles from Redis stream (filtered by exchange/symbol)."""
    r = await get_redis()
    messages = await r.xrevrange(STREAM_KLINE, count=min(limit * 3, 6000))
    result = []
    for _mid, fields in messages or []:
        payload_str = (fields or {}).get("payload")
        if not payload_str:
            continue
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            continue
        if not _match(exchange, symbol, payload):
            continue
        if str(payload.get("interval")) != str(interval):
            continue
        result.append({
            "start": payload.get("start"),
            "open": float(payload.get("open", 0)),
            "high": float(payload.get("high", 0)),
            "low": float(payload.get("low", 0)),
            "close": float(payload.get("close", 0)),
            "volume": float(payload.get("volume", 0)),
            "confirm": bool(payload.get("confirm", False)),
        })
        if len(result) >= limit:
            break
    result.reverse()
    return result


@app.get("/oi/{exchange}/{symbol}")
async def get_oi(exchange: str, symbol: str, limit: int = Query(100, le=500)):
    """REST: last N open interest points from Redis stream."""
    r = await get_redis()
    messages = await r.xrevrange(STREAM_OPEN_INTEREST, count=limit)
    result = []
    for _mid, fields in messages or []:
        payload_str = (fields or {}).get("payload")
        if not payload_str:
            continue
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            continue
        if not _match(exchange, symbol, payload):
            continue
        result.append({
            "ts": payload.get("ts"),
            "open_interest": float(payload.get("open_interest", 0)),
            "open_interest_value": float(payload["open_interest_value"]) if payload.get("open_interest_value") is not None else None,
        })
        if len(result) >= limit:
            break
    result.reverse()
    return result


@app.get("/liquidations/{exchange}/{symbol}")
async def get_liquidations(
    exchange: str,
    symbol: str,
    limit: int = Query(100, le=500),
):
    """REST: last N liquidations from Redis stream (ts, price, quantity, side)."""
    r = await get_redis()
    messages = await r.xrevrange(STREAM_LIQUIDATIONS, count=limit)
    result = []
    for _mid, fields in messages or []:
        payload_str = (fields or {}).get("payload")
        if not payload_str:
            continue
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            continue
        if not _match(exchange, symbol, payload):
            continue
        result.append({
            "ts": payload.get("ts"),
            "price": float(payload.get("price", 0)),
            "quantity": float(payload.get("quantity", 0)),
            "side": payload.get("side", ""),
        })
        if len(result) >= limit:
            break
    result.reverse()
    return result


# --- History (cold storage or Redis fallback) ---


async def _cold_conn():
    if not COLD_STORAGE_URL:
        return None
    try:
        import asyncpg
        return await asyncpg.connect(COLD_STORAGE_URL)
    except Exception:
        return None


@app.get("/history/trades/{exchange}/{symbol}")
async def history_trades(
    exchange: str,
    symbol: str,
    from_ts: int = Query(0, description="Start timestamp ms"),
    to_ts: int = Query(0, description="End timestamp ms (0 = now)"),
    limit: int = Query(500, le=5000),
):
    """REST: trades in period from cold storage or Redis."""
    conn = await _cold_conn()
    if conn:
        try:
            to_ts = to_ts or (2**62)
            rows = await conn.fetch(
                "SELECT side, price, size, ts, trade_id FROM trades WHERE exchange=$1 AND symbol=$2 AND ts >= $3 AND ts <= $4 ORDER BY ts LIMIT $5",
                exchange, symbol, from_ts, to_ts, limit,
            )
            await conn.close()
            return [{"side": r["side"], "price": float(r["price"]), "size": float(r["size"]), "ts": r["ts"], "trade_id": r["trade_id"]} for r in rows]
        except Exception:
            if conn:
                await conn.close()
    r = await get_redis()
    key = REDIS_KEY_TRADES.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -limit, -1)
    data = [json.loads(x) for x in (items or [])]
    if from_ts or to_ts:
        data = [t for t in data if (not from_ts or t.get("ts", 0) >= from_ts) and (not to_ts or t.get("ts", 0) <= to_ts)]
    return data[-limit:]




def main():
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--redis", default="redis://localhost:6379")
    args = parser.parse_args()
    os.environ["REDIS_URL"] = args.redis
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
