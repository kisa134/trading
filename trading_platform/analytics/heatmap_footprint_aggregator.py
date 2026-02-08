"""
Heatmap / footprint aggregator: reads orderbook slices and trades from Redis.
- Samples orderbook by time (250ms/1s), volume by price bins -> heatmap_slices.
- By bars (1m): footprint (volume_bid, volume_ask, delta per price) -> footprint_bars.
Writes to Redis and to streams heatmap_slices, footprint_bars.
"""
import asyncio
import json
import argparse
import time
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import redis.asyncio as redis

from shared.streams import (
    STREAM_HEATMAP_SLICES,
    STREAM_FOOTPRINT_BARS,
    REDIS_KEY_ORDERBOOK_SLICES,
    REDIS_KEY_TRADES,
    REDIS_KEY_HEATMAP,
    REDIS_KEY_FOOTPRINT,
)

HEATMAP_INTERVAL_MS = 500
FOOTPRINT_BAR_MS = 60000
PRICE_BIN_PCT = 0.0001
HEATMAP_MAXLEN = 500
FOOTPRINT_MAXLEN = 200


async def run_heatmap_footprint(redis_url: str, exchange: str = "bybit", symbol: str = "BTCUSDT"):
    r = redis.from_url(redis_url, decode_responses=True)
    slices_key = REDIS_KEY_ORDERBOOK_SLICES.format(exchange=exchange, symbol=symbol)
    trades_key = REDIS_KEY_TRADES.format(exchange=exchange, symbol=symbol)
    heatmap_key = REDIS_KEY_HEATMAP.format(exchange=exchange, symbol=symbol)
    footprint_key = REDIS_KEY_FOOTPRINT.format(exchange=exchange, symbol=symbol)
    last_heat_ts = 0
    bar_start_ts: int | None = None
    bar_trades: list = []

    while True:
        try:
            await asyncio.sleep(0.25)
            now_ms = int(time.time() * 1000)

            # Heatmap: sample latest slice every HEATMAP_INTERVAL_MS
            if now_ms - last_heat_ts >= HEATMAP_INTERVAL_MS:
                raw = await r.lrange(slices_key, -1, -1)
                if raw:
                    try:
                        snap = json.loads(raw[0])
                    except json.JSONDecodeError:
                        snap = None
                    if snap:
                        ts = int(snap.get("ts", now_ms))
                        bids = snap.get("bids", [])
                        asks = snap.get("asks", [])
                        if bids or asks:
                            mid = 0.0
                            if bids and asks:
                                mid = (bids[0][0] + asks[0][0]) / 2
                            elif bids:
                                mid = bids[0][0]
                            elif asks:
                                mid = asks[0][0]
                            step = max(mid * PRICE_BIN_PCT, 0.01)
                            bins = defaultdict(lambda: [0.0, 0.0])
                            for p, s in bids:
                                b = round(p / step) * step
                                bins[b][0] += s
                            for p, s in asks:
                                b = round(p / step) * step
                                bins[b][1] += s
                            rows = [{"price": p, "vol_bid": v[0], "vol_ask": v[1]} for p, v in sorted(bins.items())]
                            heat = {"exchange": exchange, "symbol": symbol, "ts": ts, "rows": rows}
                            payload = json.dumps(heat)
                            await r.xadd(STREAM_HEATMAP_SLICES, {"payload": payload}, maxlen=10000)
                            await r.rpush(heatmap_key, payload)
                            await r.ltrim(heatmap_key, -HEATMAP_MAXLEN, -1)
                            last_heat_ts = now_ms

            # Footprint: 1m bars from trades
            raw_trades = await r.lrange(trades_key, -2000, -1)
            trades = []
            for x in raw_trades or []:
                try:
                    trades.append(json.loads(x))
                except json.JSONDecodeError:
                    pass
            if not trades:
                continue
            # Align to 1m bar
            bar_ms = FOOTPRINT_BAR_MS
            latest_ts = max(t.get("ts", 0) for t in trades)
            current_bar_start = (latest_ts // bar_ms) * bar_ms
            if bar_start_ts is None:
                bar_start_ts = current_bar_start
            if current_bar_start > bar_start_ts:
                # Emit previous bar
                bar_trades = [t for t in trades if bar_start_ts <= t.get("ts", 0) < bar_start_ts + bar_ms]
                if bar_trades:
                    prices = [t.get("price", 0) for t in bar_trades]
                    mid = sum(prices) / len(prices) if prices else 0
                    step = max(mid * PRICE_BIN_PCT, 0.01)
                    levels = defaultdict(lambda: [0.0, 0.0])
                    for t in bar_trades:
                        p = float(t.get("price", 0))
                        s = float(t.get("size", t.get("volume", 0)))
                        side = (t.get("side") or "").lower()
                        b = round(p / step) * step
                        if side in ("buy", "bid"):
                            levels[b][0] += s
                        else:
                            levels[b][1] += s
                    sorted_items = sorted(levels.items())
                    level_list = [{"price": p, "vol_bid": v[0], "vol_ask": v[1], "delta": v[0] - v[1]} for p, v in sorted_items]
                    # POC: level with max total volume
                    poc_price: float | None = None
                    if level_list:
                        best = max(level_list, key=lambda x: x["vol_bid"] + x["vol_ask"])
                        poc_price = best["price"]
                    # Imbalance: buy vol at level >= 3x sell vol at level below (or vice versa)
                    IMBALANCE_RATIO = 3.0
                    imbalance_levels: list[dict] = []
                    for i, lev in enumerate(level_list):
                        vol_bid, vol_ask = lev["vol_bid"], lev["vol_ask"]
                        # compare with level below (index i+1)
                        if i + 1 < len(level_list):
                            below = level_list[i + 1]
                            if vol_bid >= IMBALANCE_RATIO * below["vol_ask"] and below["vol_ask"] > 0:
                                imbalance_levels.append({"price": lev["price"], "side": "buy", "ratio": round(vol_bid / below["vol_ask"], 2)})
                            if vol_ask >= IMBALANCE_RATIO * below["vol_bid"] and below["vol_bid"] > 0:
                                imbalance_levels.append({"price": lev["price"], "side": "sell", "ratio": round(vol_ask / below["vol_bid"], 2)})
                    footprint = {
                        "exchange": exchange,
                        "symbol": symbol,
                        "start": bar_start_ts,
                        "end": bar_start_ts + bar_ms,
                        "levels": level_list,
                        "poc_price": poc_price,
                        "imbalance_levels": imbalance_levels,
                    }
                    payload = json.dumps(footprint)
                    await r.xadd(STREAM_FOOTPRINT_BARS, {"payload": payload}, maxlen=5000)
                    await r.rpush(footprint_key, payload)
                    await r.ltrim(footprint_key, -FOOTPRINT_MAXLEN, -1)
                bar_start_ts = current_bar_start

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[heatmap_footprint] Error: {e}")
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379")
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()
    asyncio.run(run_heatmap_footprint(args.redis, args.exchange, args.symbol))


if __name__ == "__main__":
    main()
