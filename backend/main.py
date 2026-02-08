"""
Backend: Bybit trades + orderbook → rolling avg, anomaly_score, orderbook state → local WS broadcast.
"""
import asyncio
import json
import argparse
import time
from collections import deque

import websockets

# --- Config (CLI overrides) ---
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_PORT = 8765
BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/linear"
ROLLING_WINDOW = 100
ANOMALY_SCORE_MIN = 0.01
ANOMALY_SCORE_MAX = 10.0
ORDERBOOK_DEPTH = 200
ORDERBOOK_THROTTLE_MS = 80
ORDERBOOK_HISTORY_SIZE = 300
ORDERBOOK_HISTORY_BATCH_MS = 500
ORDERBOOK_HISTORY_BATCH_SIZE = 5
KLINE_INTERVAL = 1
KLINE_BUFFER_SIZE = 200
FOOTPRINT_PRICE_STEP_PCT = 0.0001
ICEBERG_WINDOW_MS = 10000
ICEBERG_CHECK_MS = 2000
ICEBERG_VOLUME_MULT = 2.5
ICEBERG_PRICE_STEP_PCT = 0.0001

# Shared: queue of JSON strings to broadcast; set of connected frontend clients
broadcast_queue: asyncio.Queue = None
clients: set = None
orderbook_history: deque = None
recent_trades: deque = None
current_bids: dict = None
current_asks: dict = None


async def local_ws_server(port: int):
    """WebSocket server: accept connections, broadcast messages from queue."""
    global clients

    async def handler(ws):
        clients.add(ws)
        try:
            async for _ in ws:
                pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            clients.discard(ws)

    async with websockets.serve(handler, "localhost", port):
        await asyncio.Future()


async def broadcaster(port: int):
    """Consume queue and send each message to all connected clients."""
    global broadcast_queue, clients
    while True:
        msg = await broadcast_queue.get()
        if not clients:
            continue
        dead = set()
        for ws in clients:
            try:
                await ws.send(msg)
            except Exception:
                dead.add(ws)
        for ws in dead:
            clients.discard(ws)


async def orderbook_history_sender():
    """Every ORDERBOOK_HISTORY_BATCH_MS ms, send last N snapshots to frontend for heatmap."""
    global broadcast_queue, orderbook_history
    while True:
        await asyncio.sleep(ORDERBOOK_HISTORY_BATCH_MS / 1000.0)
        if orderbook_history is None or len(orderbook_history) == 0:
            continue
        snapshots = list(orderbook_history)[-ORDERBOOK_HISTORY_BATCH_SIZE:]
        payload = {"type": "orderbook_history", "snapshots": snapshots}
        await broadcast_queue.put(json.dumps(payload))


def _apply_orderbook_snapshot(bids: dict, asks: dict, data: dict) -> None:
    """Replace orderbook with snapshot."""
    bids.clear()
    asks.clear()
    for entry in data.get("b", []):
        if len(entry) >= 2:
            price, size = float(entry[0]), float(entry[1])
            if size > 0:
                bids[price] = size
    for entry in data.get("a", []):
        if len(entry) >= 2:
            price, size = float(entry[0]), float(entry[1])
            if size > 0:
                asks[price] = size


def _apply_orderbook_delta(bids: dict, asks: dict, data: dict) -> None:
    """Apply delta: size=0 delete, else insert/update."""
    for entry in data.get("b", []):
        if len(entry) >= 2:
            price, size = float(entry[0]), float(entry[1])
            if size <= 0:
                bids.pop(price, None)
            else:
                bids[price] = size
    for entry in data.get("a", []):
        if len(entry) >= 2:
            price, size = float(entry[0]), float(entry[1])
            if size <= 0:
                asks.pop(price, None)
            else:
                asks[price] = size


def _orderbook_to_lists(bids: dict, asks: dict, limit: int = 50):
    """Return bids/asks as sorted lists of [price, size] for frontend."""
    b = sorted(bids.items(), key=lambda x: -x[0])[:limit]
    a = sorted(asks.items(), key=lambda x: x[0])[:limit]
    return [[p, s] for p, s in b], [[p, s] for p, s in a]


def _size_at_level(snap: dict, level: float, side: str, step: float) -> float:
    """Get size at price level from snapshot (bids or asks)."""
    arr = snap.get("bids" if side == "bid" else "asks", [])
    for entry in arr:
        if len(entry) < 2:
            continue
        p, s = float(entry[0]), float(entry[1])
        if abs(p - level) <= step / 2:
            return s
    return 0.0


def _detect_icebergs(
    recent_trades: deque,
    orderbook_history: deque,
    bids: dict,
    asks: dict,
    now_ts: int,
) -> list:
    """Heuristic: high trade volume at one level + orderbook replenishment at that level."""
    if not recent_trades or not orderbook_history:
        return []
    window_ms = ICEBERG_WINDOW_MS
    trades_in_window = [t for t in recent_trades if now_ts - t["ts"] < window_ms]
    if len(trades_in_window) < 5:
        return []
    best_bid = max(bids.keys()) if bids else 0.0
    best_ask = min(asks.keys()) if asks else float("inf")
    mid = (best_bid + best_ask) / 2 if (bids and asks) else (trades_in_window[-1]["price"] if trades_in_window else 0)
    step = max(mid * ICEBERG_PRICE_STEP_PCT, 0.01)
    levels_vol = {}
    for t in trades_in_window:
        price, vol, side = t["price"], t["volume"], t["side"]
        lvl = round(price / step) * step
        if lvl not in levels_vol:
            levels_vol[lvl] = {"buy": 0.0, "sell": 0.0}
        if side == "Buy":
            levels_vol[lvl]["buy"] += vol
        else:
            levels_vol[lvl]["sell"] += vol
    avg_vol = sum(t["volume"] for t in trades_in_window) / len(trades_in_window) or 1.0
    threshold = avg_vol * ICEBERG_VOLUME_MULT
    snapshots_in_window = [s for s in orderbook_history if isinstance(s, dict) and now_ts - s.get("ts", 0) < window_ms]
    snapshots_in_window.sort(key=lambda s: s.get("ts", 0))
    icebergs = []
    for level, vol in levels_vol.items():
        total = vol["buy"] + vol["sell"]
        if total < threshold:
            continue
        side = "Buy" if vol["buy"] >= vol["sell"] else "Sell"
        sizes_bid = [_size_at_level(s, level, "bid", step) for s in snapshots_in_window]
        sizes_ask = [_size_at_level(s, level, "ask", step) for s in snapshots_in_window]
        sizes = sizes_bid if side == "Buy" else sizes_ask
        replenished = False
        for i in range(len(sizes) - 2):
            if sizes[i] > sizes[i + 1] and sizes[i + 1] < sizes[i + 2] and sizes[i + 2] > 0:
                replenished = True
                break
        if replenished or total > threshold * 2:
            icebergs.append({
                "price": level,
                "side": side,
                "volume_estimate": round(total, 4),
                "ts_start": now_ts - window_ms,
                "ts_end": now_ts,
            })
    return icebergs


async def iceberg_detector():
    """Periodically detect possible iceberg levels and send to frontend."""
    global broadcast_queue, orderbook_history, recent_trades
    while True:
        await asyncio.sleep(ICEBERG_CHECK_MS / 1000.0)
        if recent_trades is None or orderbook_history is None:
            continue
        try:
            now_ts = int(time.time() * 1000)
            icebergs = _detect_icebergs(
                recent_trades,
                orderbook_history,
                current_bids or {},
                current_asks or {},
                now_ts,
            )
        except Exception:
            icebergs = []
        if not icebergs:
            continue
        payload = {"type": "iceberg", "icebergs": icebergs}
        await broadcast_queue.put(json.dumps(payload))


async def bybit_client(symbol: str):
    """Connect to Bybit, subscribe to trades + orderbook, push trades (with type) and throttled orderbook."""
    global broadcast_queue, recent_trades, current_bids, current_asks
    volumes = deque(maxlen=ROLLING_WINDOW)
    trade_topic = f"publicTrade.{symbol}"
    book_topic = f"orderbook.{ORDERBOOK_DEPTH}.{symbol}"
    kline_topic = f"kline.{KLINE_INTERVAL}.{symbol}"
    subscribe_msg = json.dumps({"op": "subscribe", "args": [trade_topic, book_topic, kline_topic]})

    bids = {}
    asks = {}
    last_orderbook_send = 0.0
    current_bids = bids
    current_asks = asks
    kline_buffer = []

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
                        side = t.get("S", "Buy")
                        ts = int(t.get("T", 0))
                        if vol <= 0:
                            continue
                        volumes.append(vol)
                        avg = sum(volumes) / len(volumes) if volumes else vol
                        avg = max(avg, 1e-12)
                        score = vol / avg
                        score = max(ANOMALY_SCORE_MIN, min(ANOMALY_SCORE_MAX, score))
                        payload = {
                            "type": "trade",
                            "price": price,
                            "volume": vol,
                            "side": side,
                            "anomaly_score": round(score, 4),
                            "ts": ts,
                        }
                        await broadcast_queue.put(json.dumps(payload))
                        if recent_trades is not None:
                            recent_trades.append({"price": price, "volume": vol, "side": side, "ts": ts})

                elif topic == book_topic:
                    msg_type = data.get("type")
                    d = data.get("data", data)
                    if msg_type == "snapshot":
                        _apply_orderbook_snapshot(bids, asks, d)
                        last_orderbook_send = 0.0
                    else:
                        _apply_orderbook_delta(bids, asks, d)

                    now = time.monotonic()
                    if (now - last_orderbook_send) * 1000 >= ORDERBOOK_THROTTLE_MS or msg_type == "snapshot":
                        last_orderbook_send = now
                        b_list, a_list = _orderbook_to_lists(bids, asks, ORDERBOOK_DEPTH)
                        payload = {"type": "orderbook", "bids": b_list, "asks": a_list}
                        await broadcast_queue.put(json.dumps(payload))
                        if orderbook_history is not None:
                            orderbook_history.append({
                                "ts": int(time.time() * 1000),
                                "bids": b_list,
                                "asks": a_list,
                            })

                elif topic == kline_topic:
                    for k in data.get("data", []):
                        start_ts = int(k.get("start", 0))
                        o = float(k.get("open", 0))
                        h = float(k.get("high", 0))
                        lo = float(k.get("low", 0))
                        c = float(k.get("close", 0))
                        vol = float(k.get("volume", 0))
                        confirm = bool(k.get("confirm", False))
                        candle = {"start": start_ts, "open": o, "high": h, "low": lo, "close": c, "volume": vol, "confirm": confirm}
                        kline_buffer[:] = [x for x in kline_buffer if x["start"] != start_ts]
                        kline_buffer.append(candle)
                        kline_buffer.sort(key=lambda x: x["start"])
                        if len(kline_buffer) > KLINE_BUFFER_SIZE:
                            kline_buffer[:] = kline_buffer[-KLINE_BUFFER_SIZE:]
                        await broadcast_queue.put(json.dumps({"type": "kline", "candle": candle}))
                        if confirm and recent_trades is not None:
                            end_ts = int(k.get("end", start_ts + 60000))
                            step = max((o + c) / 2 * FOOTPRINT_PRICE_STEP_PCT, 0.01)
                            levels_vol = {}
                            for t in recent_trades:
                                if start_ts <= t["ts"] <= end_ts:
                                    lvl = round(t["price"] / step) * step
                                    if lvl not in levels_vol:
                                        levels_vol[lvl] = {"bidVol": 0.0, "askVol": 0.0}
                                    if t["side"] == "Buy":
                                        levels_vol[lvl]["bidVol"] += t["volume"]
                                    else:
                                        levels_vol[lvl]["askVol"] += t["volume"]
                            levels = [{"price": p, "bidVol": v["bidVol"], "askVol": v["askVol"]} for p, v in sorted(levels_vol.items())]
                            await broadcast_queue.put(json.dumps({"type": "footprint", "start": start_ts, "end": end_ts, "levels": levels}))

        except websockets.exceptions.ConnectionClosed as e:
            print(f"Bybit WS closed: {e}, reconnecting...")
        except Exception as e:
            print(f"Bybit error: {e}, reconnecting...")
        await asyncio.sleep(2)


async def main():
    global broadcast_queue, orderbook_history
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Bybit symbol (e.g. BTCUSDT)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Local WS server port")
    args = parser.parse_args()

    broadcast_queue = asyncio.Queue()
    global clients, recent_trades
    clients = set()
    orderbook_history = deque(maxlen=ORDERBOOK_HISTORY_SIZE)
    recent_trades = deque(maxlen=2000)
    port = args.port
    symbol = args.symbol

    await asyncio.gather(
        local_ws_server(port),
        broadcaster(port),
        bybit_client(symbol),
        orderbook_history_sender(),
        iceberg_detector(),
    )


if __name__ == "__main__":
    asyncio.run(main())
