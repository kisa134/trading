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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Body
from fastapi.middleware.cors import CORSMiddleware

from shared.streams import (
    STREAM_ORDERBOOK_UPDATES,
    STREAM_TRADES,
    STREAM_KLINE,
    STREAM_HEATMAP_SLICES,
    STREAM_FOOTPRINT_BARS,
    STREAM_EVENTS,
    STREAM_SCORES_TREND,
    STREAM_SCORES_EXHAUSTION,
    STREAM_SIGNALS_RULE_REVERSAL,
    STREAM_OPEN_INTEREST,
    STREAM_LIQUIDATIONS,
    REDIS_KEY_DOM,
    REDIS_KEY_TRADES,
    REDIS_KEY_HEATMAP,
    REDIS_KEY_FOOTPRINT,
    REDIS_KEY_EVENTS,
    REDIS_KEY_TAPE,
    REDIS_KEY_SCORES_TREND,
    REDIS_KEY_SCORES_EXHAUSTION,
    REDIS_KEY_SIGNALS_RULE,
    REDIS_KEY_IMBALANCE,
    REDIS_KEY_IMBALANCE_HISTORY,
    REDIS_KEY_OI,
    REDIS_KEY_LIQUIDATIONS,
    STREAM_AI_SNAPSHOTS,
    REDIS_KEY_AI_SNAPSHOT_BLOB,
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
_ai_controller_task: asyncio.Task | None = None


async def send_ai_response(exchange: str, symbol: str, text: str):
    """Send AI response to all WS clients subscribed to ai_response for (exchange, symbol)."""
    key = (exchange, symbol)
    async with subscribers_lock:
        targets = list(subscribers.get(key, []))
    msg = {"stream": "ai_response", "data": {"text": text}}
    payload = json.dumps(msg)
    dead = []
    for ch, ws in targets:
        if ch != "ai_response":
            continue
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append((ch, ws))
    for t in dead:
        async with subscribers_lock:
            s = subscribers.get(key, set())
            s.discard(t)
            if not s:
                subscribers.pop(key, None)


@app.on_event("startup")
async def startup():
    global _broadcast_task, _ai_controller_task
    await get_redis()
    _broadcast_task = asyncio.create_task(broadcast_worker())
    try:
        from services.market_context_builder import get_or_build_context
        from services.ai.router import route_multimodal
        from services.ai.controller import run_controller
        _ai_controller_task = asyncio.create_task(
            run_controller(get_redis, get_or_build_context, route_multimodal, send_ai_response)
        )
    except Exception as e:
        print(f"[startup] AI controller not started: {e}")


@app.on_event("shutdown")
async def shutdown():
    global redis_client, _broadcast_task, _ai_controller_task
    if _ai_controller_task:
        _ai_controller_task.cancel()
        try:
            await _ai_controller_task
        except asyncio.CancelledError:
            pass
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
    STREAM_HEATMAP_SLICES: "heatmap_stream",
    STREAM_FOOTPRINT_BARS: "footprint_stream",
    STREAM_EVENTS: "events_stream",
    STREAM_SCORES_TREND: "scores",
    STREAM_SCORES_EXHAUSTION: "exhaustion_absorption",
    STREAM_SIGNALS_RULE_REVERSAL: "signals",
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
        STREAM_HEATMAP_SLICES: "$",
        STREAM_FOOTPRINT_BARS: "$",
        STREAM_EVENTS: "$",
        STREAM_SCORES_TREND: "$",
        STREAM_SCORES_EXHAUSTION: "$",
        STREAM_SIGNALS_RULE_REVERSAL: "$",
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


# --- AI snapshot (visual capture for LLM) ---
AI_SNAPSHOT_MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 MB
AI_SNAPSHOT_BLOB_TTL_SEC = 300


@app.post("/ai/snapshot", status_code=202)
async def ai_snapshot(
    body: dict = Body(..., embed=False),
):
    """Accept canvas snapshot (base64 JPEG), store in Redis, push to stream for AI Controller."""
    exchange = (body.get("exchange") or "").strip() or "bybit"
    symbol = (body.get("symbol") or "").strip().upper() or "BTCUSDT"
    image_base64 = body.get("imageBase64")
    ts = int(body.get("ts") or 0) or __import__("time").time() * 1000
    trigger = body.get("trigger") or "manual"
    if not image_base64 or not isinstance(image_base64, str):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="imageBase64 required")
    r = await get_redis()
    snapshot_id = __import__("uuid").uuid4().hex
    blob_key = REDIS_KEY_AI_SNAPSHOT_BLOB.format(exchange=exchange, symbol=symbol, ts=ts)
    await r.set(blob_key, image_base64, ex=AI_SNAPSHOT_BLOB_TTL_SEC)
    await r.xadd(
        STREAM_AI_SNAPSHOTS,
        {"payload": json.dumps({
            "exchange": exchange,
            "symbol": symbol,
            "ts": ts,
            "snapshotId": snapshot_id,
            "trigger": trigger,
            "blobKey": blob_key,
        })},
        maxlen=1000,
    )
    await r.sadd("ai:active_pairs", f"{exchange}:{symbol}")
    return {"snapshotId": snapshot_id, "ts": ts}


@app.post("/ai/predictions", status_code=201)
async def ai_save_prediction(body: dict = Body(..., embed=False)):
    """Record an AI prediction for Outcome Worker and Experience Replay."""
    from fastapi import HTTPException
    from services.ai.prediction_store import save_prediction
    exchange = (body.get("exchange") or "").strip() or "bybit"
    symbol = (body.get("symbol") or "").strip().upper() or "BTCUSDT"
    ts_prediction = int(body.get("ts_prediction") or 0) or int(__import__("time").time() * 1000)
    horizon_minutes = int(body.get("horizon_minutes") or 15)
    price_at_prediction = float(body.get("price_at_prediction") or 0)
    if not price_at_prediction:
        raise HTTPException(status_code=400, detail="price_at_prediction required")
    target_price = body.get("target_price") and float(body["target_price"]) or None
    direction = (body.get("direction") or "").strip() or None
    expected_range_low = body.get("expected_range_low") is not None and float(body["expected_range_low"]) or None
    expected_range_high = body.get("expected_range_high") is not None and float(body["expected_range_high"]) or None
    snapshot_ref = (body.get("snapshot_ref") or "").strip() or None
    context_snapshot = body.get("context_snapshot") if isinstance(body.get("context_snapshot"), dict) else None
    models_used = body.get("models_used")
    r = await get_redis()
    prediction_id = await save_prediction(
        r, exchange, symbol, ts_prediction, horizon_minutes, price_at_prediction,
        target_price=target_price, direction=direction,
        expected_range_low=expected_range_low, expected_range_high=expected_range_high,
        snapshot_ref=snapshot_ref, context_snapshot=context_snapshot, models_used=models_used,
    )
    try:
        from services.graph.writer import write_prediction
        text = f"direction={direction or 'n/a'} target={target_price} range=[{expected_range_low},{expected_range_high}]"
        write_prediction(str(prediction_id), exchange, symbol, ts_prediction, text, horizon_minutes)
    except Exception:
        pass
    return {"predictionId": prediction_id, "ts_prediction": ts_prediction}


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


@app.get("/heatmap/{exchange}/{symbol}")
async def get_heatmap(exchange: str, symbol: str, limit: int = 100):
    """REST: last N heatmap slices from Redis."""
    r = await get_redis()
    key = REDIS_KEY_HEATMAP.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -limit, -1)
    return [json.loads(x) for x in (items or [])]


@app.get("/footprint/{exchange}/{symbol}")
async def get_footprint(exchange: str, symbol: str, limit: int = 50):
    """REST: last N footprint bars from Redis."""
    r = await get_redis()
    key = REDIS_KEY_FOOTPRINT.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -limit, -1)
    return [json.loads(x) for x in (items or [])]


@app.get("/events/{exchange}/{symbol}")
async def get_events(exchange: str, symbol: str, limit: int = 50):
    """REST: last N events (iceberg, wall, spoof) from Redis."""
    r = await get_redis()
    key = REDIS_KEY_EVENTS.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -limit, -1)
    return [json.loads(x) for x in (items or [])]


@app.get("/tape/{exchange}/{symbol}")
async def get_tape(exchange: str, symbol: str):
    """REST: current tape aggregates (1s/5s/1m buy/sell/delta) from Redis."""
    r = await get_redis()
    key = REDIS_KEY_TAPE.format(exchange=exchange, symbol=symbol)
    raw = await r.get(key)
    if not raw:
        return {}
    return json.loads(raw)


@app.get("/scores/trend/{exchange}/{symbol}")
async def get_scores_trend(exchange: str, symbol: str, limit: int = 200):
    """REST: last N trend score points."""
    r = await get_redis()
    key = REDIS_KEY_SCORES_TREND.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -limit, -1)
    return [json.loads(x) for x in (items or [])]


@app.get("/scores/exhaustion/{exchange}/{symbol}")
async def get_scores_exhaustion(exchange: str, symbol: str, limit: int = 200):
    """REST: last N exhaustion/absorption points."""
    r = await get_redis()
    key = REDIS_KEY_SCORES_EXHAUSTION.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -limit, -1)
    return [json.loads(x) for x in (items or [])]


@app.get("/signals/rule/{exchange}/{symbol}")
async def get_signals_rule(exchange: str, symbol: str, limit: int = 200):
    """REST: last N rule-based reversal signals."""
    r = await get_redis()
    key = REDIS_KEY_SIGNALS_RULE.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -limit, -1)
    return [json.loads(x) for x in (items or [])]


@app.get("/imbalance/{exchange}/{symbol}")
async def get_imbalance(
    exchange: str,
    symbol: str,
    limit: int = Query(0, ge=0, le=500, description="History length (0 = current only)"),
):
    """REST: current order book imbalance % and optionally last N history points."""
    r = await get_redis()
    key_cur = REDIS_KEY_IMBALANCE.format(exchange=exchange, symbol=symbol)
    raw = await r.get(key_cur)
    current = json.loads(raw) if raw else {"ts": 0, "imbalance_pct": 0}
    if limit <= 0:
        return {"current": current, "history": []}
    key_hist = REDIS_KEY_IMBALANCE_HISTORY.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key_hist, -limit, -1)
    history = [json.loads(x) for x in (items or [])]
    return {"current": current, "history": history}


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


@app.get("/history/heatmap/{exchange}/{symbol}")
async def history_heatmap(
    exchange: str,
    symbol: str,
    from_ts: int = Query(0),
    to_ts: int = Query(0),
    limit: int = Query(200, le=2000),
):
    """REST: heatmap rows in period from cold storage or Redis."""
    conn = await _cold_conn()
    if conn:
        try:
            to_ts = to_ts or (2**62)
            rows = await conn.fetch(
                "SELECT ts, price_bin, volume_bid, volume_ask FROM heatmap_rows WHERE exchange=$1 AND symbol=$2 AND ts >= $3 AND ts <= $4 ORDER BY ts LIMIT $5",
                exchange, symbol, from_ts, to_ts, limit,
            )
            await conn.close()
            by_ts = {}
            for r in rows:
                ts = r["ts"]
                if ts not in by_ts:
                    by_ts[ts] = {"ts": ts, "rows": []}
                by_ts[ts]["rows"].append({"price": float(r["price_bin"]), "vol_bid": float(r["volume_bid"]), "vol_ask": float(r["volume_ask"])})
            return list(by_ts.values())
        except Exception:
            if conn:
                await conn.close()
    r = await get_redis()
    key = REDIS_KEY_HEATMAP.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -limit, -1)
    return [json.loads(x) for x in (items or [])]


@app.get("/history/footprint/{exchange}/{symbol}")
async def history_footprint(
    exchange: str,
    symbol: str,
    from_ts: int = Query(0),
    to_ts: int = Query(0),
    limit: int = Query(100, le=500),
):
    """REST: footprint bars in period from cold storage or Redis."""
    conn = await _cold_conn()
    if conn:
        try:
            to_ts = to_ts or (2**62)
            rows = await conn.fetch(
                "SELECT bar_start, bar_end, price, volume_bid, volume_ask, delta FROM footprint_bars WHERE exchange=$1 AND symbol=$2 AND bar_start >= $3 AND bar_start <= $4 ORDER BY bar_start LIMIT $5",
                exchange, symbol, from_ts, to_ts, limit,
            )
            await conn.close()
            by_bar = {}
            for r in rows:
                start = r["bar_start"]
                if start not in by_bar:
                    by_bar[start] = {"start": start, "end": r["bar_end"], "levels": []}
                by_bar[start]["levels"].append({"price": float(r["price"]), "vol_bid": float(r["volume_bid"]), "vol_ask": float(r["volume_ask"]), "delta": float(r["delta"])})
            return list(by_bar.values())
        except Exception:
            if conn:
                await conn.close()
    r = await get_redis()
    key = REDIS_KEY_FOOTPRINT.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -limit, -1)
    return [json.loads(x) for x in (items or [])]


@app.get("/history/events/{exchange}/{symbol}")
async def history_events(
    exchange: str,
    symbol: str,
    from_ts: int = Query(0),
    to_ts: int = Query(0),
    limit: int = Query(100, le=500),
):
    """REST: events in period from cold storage or Redis."""
    conn = await _cold_conn()
    if conn:
        try:
            to_ts = to_ts or (2**62)
            rows = await conn.fetch(
                "SELECT type, price, side, volume, ts_start, ts_end, payload FROM events WHERE exchange=$1 AND symbol=$2 AND ts_start >= $3 AND ts_start <= $4 ORDER BY ts_start LIMIT $5",
                exchange, symbol, from_ts, to_ts, limit,
            )
            await conn.close()
            return [{"type": r["type"], "price": float(r["price"]) if r["price"] else None, "side": r["side"], "volume": float(r["volume"]) if r["volume"] else None, "ts_start": r["ts_start"], "ts_end": r["ts_end"], "payload": r["payload"]} for r in rows]
        except Exception:
            if conn:
                await conn.close()
    r = await get_redis()
    key = REDIS_KEY_EVENTS.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -limit, -1)
    return [json.loads(x) for x in (items or [])]


@app.get("/history/scores/trend/{exchange}/{symbol}")
async def history_scores_trend(exchange: str, symbol: str, limit: int = 500):
    """REST: trend scores history (Redis fallback)."""
    r = await get_redis()
    key = REDIS_KEY_SCORES_TREND.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -limit, -1)
    return [json.loads(x) for x in (items or [])]


@app.get("/history/scores/exhaustion/{exchange}/{symbol}")
async def history_scores_exhaustion(exchange: str, symbol: str, limit: int = 500):
    """REST: exhaustion/absorption history (Redis fallback)."""
    r = await get_redis()
    key = REDIS_KEY_SCORES_EXHAUSTION.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -limit, -1)
    return [json.loads(x) for x in (items or [])]


@app.get("/history/signals/rule/{exchange}/{symbol}")
async def history_signals_rule(exchange: str, symbol: str, limit: int = 500):
    """REST: rule-based signals history (Redis fallback)."""
    r = await get_redis()
    key = REDIS_KEY_SIGNALS_RULE.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -limit, -1)
    return [json.loads(x) for x in (items or [])]


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
