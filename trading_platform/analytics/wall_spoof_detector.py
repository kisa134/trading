"""
Wall / spoof detector: reads orderbook slices from Redis.
- Volume at level >> median of neighbors and persists -> WALL_CREATED / WALL_REMOVED.
- Large limit appeared and disappeared without fill -> SPOOF_SIGNAL.
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

from shared.streams import STREAM_EVENTS, REDIS_KEY_EVENTS, REDIS_KEY_ORDERBOOK_SLICES, EVENTS_MAXLEN

WALL_MEDIAN_MULT = 3.0
WALL_PERSIST_MS = 5000
WALL_CHECK_MS = 2000
SPOOF_DISAPPEAR_MS = 3000
SPOOF_SIZE_MULT = 2.0
LEVELS_LOOK = 20


def _level_volumes(snap: dict, side: str, limit: int) -> list[tuple[float, float]]:
    arr = snap.get("bids" if side == "bid" else "asks", [])
    items = []
    for entry in (arr or [])[:limit]:
        if len(entry) >= 2:
            items.append((float(entry[0]), float(entry[1])))
    if side == "ask":
        items.sort(key=lambda x: x[0])
    else:
        items.sort(key=lambda x: -x[0])
    return items


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n else 0.0


async def run_wall_spoof_detector(redis_url: str, exchange: str = "bybit", symbol: str = "BTCUSDT"):
    r = redis.from_url(redis_url, decode_responses=True)
    slices_key = REDIS_KEY_ORDERBOOK_SLICES.format(exchange=exchange, symbol=symbol)
    events_key = REDIS_KEY_EVENTS.format(exchange=exchange, symbol=symbol)
    # recent slices for spoof: (ts, {level: size})
    recent_bid_levels: deque = deque(maxlen=50)
    recent_ask_levels: deque = deque(maxlen=50)
    wall_seen: set[tuple[str, float]] = set()

    while True:
        try:
            await asyncio.sleep(WALL_CHECK_MS / 1000.0)
            raw_slices = await r.lrange(slices_key, -30, -1)
            snapshots = []
            for x in raw_slices or []:
                try:
                    snapshots.append(json.loads(x))
                except json.JSONDecodeError:
                    pass
            if not snapshots:
                continue
            latest = snapshots[-1]
            ts = int(latest.get("ts", time.time() * 1000))
            now_ts = ts

            # Wall detection: levels where size >> median(neighbors)
            bids = _level_volumes(latest, "bid", LEVELS_LOOK)
            asks = _level_volumes(latest, "ask", LEVELS_LOOK)
            events = []

            for side, levels in [("bid", bids), ("ask", asks)]:
                if len(levels) < 5:
                    continue
                for i, (price, size) in enumerate(levels):
                    if size <= 0:
                        continue
                    neighbors = []
                    for j in range(max(0, i - 2), min(len(levels), i + 3)):
                        if j != i:
                            neighbors.append(levels[j][1])
                    med = _median(neighbors)
                    if med <= 0:
                        continue
                    if size >= med * WALL_MEDIAN_MULT:
                        key = (side, price)
                        if key not in wall_seen:
                            wall_seen.add(key)
                            events.append({
                                "type": "WALL_CREATED",
                                "exchange": exchange,
                                "symbol": symbol,
                                "side": side,
                                "price": price,
                                "size": size,
                                "ts": now_ts,
                            })
                    else:
                        wall_seen.discard((side, price))

            # Spoof: large level that appeared and then disappeared (simplified: level was in prev, not in latest with same size)
            if len(snapshots) >= 2:
                prev = snapshots[-2]
                prev_bids = {p: s for p, s in _level_volumes(prev, "bid", LEVELS_LOOK)}
                prev_asks = {p: s for p, s in _level_volumes(prev, "ask", LEVELS_LOOK)}
                curr_bids = {p: s for p, s in bids}
                curr_asks = {p: s for p, s in asks}
                avg_bid = sum(curr_bids.values()) / len(curr_bids) if curr_bids else 0
                avg_ask = sum(curr_asks.values()) / len(curr_asks) if curr_asks else 0
                for p, s in prev_bids.items():
                    if s >= avg_bid * SPOOF_SIZE_MULT and curr_bids.get(p, 0) < s * 0.5:
                        events.append({
                            "type": "SPOOF_SIGNAL",
                            "exchange": exchange,
                            "symbol": symbol,
                            "side": "bid",
                            "price": p,
                            "size": s,
                            "ts": now_ts,
                        })
                for p, s in prev_asks.items():
                    if s >= avg_ask * SPOOF_SIZE_MULT and curr_asks.get(p, 0) < s * 0.5:
                        events.append({
                            "type": "SPOOF_SIGNAL",
                            "exchange": exchange,
                            "symbol": symbol,
                            "side": "ask",
                            "price": p,
                            "size": s,
                            "ts": now_ts,
                        })

            for event in events:
                payload = json.dumps(event)
                await r.xadd(STREAM_EVENTS, {"payload": payload}, maxlen=10000)
                await r.rpush(events_key, payload)
                await r.ltrim(events_key, -EVENTS_MAXLEN, -1)

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[wall_spoof] Error: {e}")
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379")
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()
    asyncio.run(run_wall_spoof_detector(args.redis, args.exchange, args.symbol))


if __name__ == "__main__":
    main()
