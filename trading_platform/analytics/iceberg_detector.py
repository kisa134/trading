"""
Iceberg detector: reads recent trades and orderbook slices from Redis,
heuristic (high volume at one level + orderbook replenishment), emits ICEBERG_DETECTED to events stream.
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

from shared.streams import STREAM_EVENTS, REDIS_KEY_EVENTS, REDIS_KEY_TRADES, REDIS_KEY_ORDERBOOK_SLICES, EVENTS_MAXLEN

ICEBERG_WINDOW_MS = 10000
ICEBERG_CHECK_MS = 2000
ICEBERG_VOLUME_MULT = 2.5
ICEBERG_PRICE_STEP_PCT = 0.0001
EVENT_TYPE_ICEBERG = "ICEBERG_DETECTED"


def _size_at_level(snap: dict, level: float, side: str, step: float) -> float:
    arr = snap.get("bids" if side == "bid" else "asks", [])
    for entry in arr:
        if len(entry) < 2:
            continue
        p, s = float(entry[0]), float(entry[1])
        if abs(p - level) <= step / 2:
            return s
    return 0.0


def _detect_icebergs(recent_trades: list, orderbook_snapshots: list, now_ts: int) -> list:
    if not recent_trades or not orderbook_snapshots:
        return []
    window_ms = ICEBERG_WINDOW_MS
    trades_in_window = [t for t in recent_trades if now_ts - t.get("ts", 0) < window_ms]
    if len(trades_in_window) < 5:
        return []
    prices = [t.get("price", 0) for t in trades_in_window if t.get("price")]
    mid = sum(prices) / len(prices) if prices else 0
    step = max(mid * ICEBERG_PRICE_STEP_PCT, 0.01)
    levels_vol = {}
    for t in trades_in_window:
        price = float(t.get("price", 0))
        vol = float(t.get("size", t.get("volume", 0)))
        side = t.get("side", "Sell")
        lvl = round(price / step) * step
        if lvl not in levels_vol:
            levels_vol[lvl] = {"buy": 0.0, "sell": 0.0}
        if (side or "").lower() in ("buy", "bid"):
            levels_vol[lvl]["buy"] += vol
        else:
            levels_vol[lvl]["sell"] += vol
    avg_vol = sum(float(t.get("size", t.get("volume", 0))) for t in trades_in_window) / len(trades_in_window) or 1.0
    threshold = avg_vol * ICEBERG_VOLUME_MULT
    snapshots_in_window = [s for s in orderbook_snapshots if isinstance(s, dict) and now_ts - s.get("ts", 0) < window_ms]
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


async def run_iceberg_detector(redis_url: str, exchange: str = "bybit", symbol: str = "BTCUSDT"):
    r = redis.from_url(redis_url, decode_responses=True)
    trades_key = REDIS_KEY_TRADES.format(exchange=exchange, symbol=symbol)
    slices_key = REDIS_KEY_ORDERBOOK_SLICES.format(exchange=exchange, symbol=symbol)
    events_key = REDIS_KEY_EVENTS.format(exchange=exchange, symbol=symbol)

    while True:
        try:
            await asyncio.sleep(ICEBERG_CHECK_MS / 1000.0)
            raw_trades = await r.lrange(trades_key, -500, -1)
            raw_slices = await r.lrange(slices_key, -100, -1)
            recent_trades = []
            for x in raw_trades or []:
                try:
                    recent_trades.append(json.loads(x))
                except json.JSONDecodeError:
                    pass
            orderbook_snapshots = []
            for x in raw_slices or []:
                try:
                    orderbook_snapshots.append(json.loads(x))
                except json.JSONDecodeError:
                    pass
            now_ts = int(time.time() * 1000)
            icebergs = _detect_icebergs(recent_trades, orderbook_snapshots, now_ts)
            if not icebergs:
                continue
            event = {
                "type": EVENT_TYPE_ICEBERG,
                "exchange": exchange,
                "symbol": symbol,
                "ts": now_ts,
                "icebergs": icebergs,
            }
            payload = json.dumps(event)
            await r.xadd(STREAM_EVENTS, {"payload": payload}, maxlen=10000)
            await r.rpush(events_key, payload)
            await r.ltrim(events_key, -EVENTS_MAXLEN, -1)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[iceberg] Error: {e}")
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379")
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()
    asyncio.run(run_iceberg_detector(args.redis, args.exchange, args.symbol))


if __name__ == "__main__":
    main()
