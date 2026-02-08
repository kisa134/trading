"""
Feature engine: orderbook score (Score_orderbook) from orderbook slices and events.
Stores latest score in Redis for trend engine.
"""
import asyncio
import json
import argparse
import time
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import redis.asyncio as redis

from shared.streams import (
    REDIS_KEY_ORDERBOOK_SLICES,
    REDIS_KEY_EVENTS,
    REDIS_KEY_SCORE_ORDERBOOK,
    REDIS_KEY_IMBALANCE,
    REDIS_KEY_IMBALANCE_HISTORY,
    IMBALANCE_HISTORY_MAXLEN,
)

LEVELS_LOOK = 20
EVENT_LOOKBACK_MS = 300000


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    return s[len(s) // 2]


def _score_ratio(ratio: float) -> float:
    if ratio >= 5:
        return 6.0
    if ratio >= 3:
        return 4.0
    if ratio >= 2:
        return 2.0
    return 0.0


async def run_feature_engine_orderbook(redis_url: str, exchange: str, symbol: str):
    r = redis.from_url(redis_url, decode_responses=True)
    slices_key = REDIS_KEY_ORDERBOOK_SLICES.format(exchange=exchange, symbol=symbol)
    events_key = REDIS_KEY_EVENTS.format(exchange=exchange, symbol=symbol)

    while True:
        try:
            raw_slice = await r.lrange(slices_key, -1, -1)
            if raw_slice:
                try:
                    snap = json.loads(raw_slice[0])
                except json.JSONDecodeError:
                    snap = None
            else:
                snap = None
            if not snap:
                await asyncio.sleep(1)
                continue
            bids = snap.get("bids", [])[:LEVELS_LOOK]
            asks = snap.get("asks", [])[:LEVELS_LOOK]
            sizes = [float(s) for _, s in bids + asks if s is not None]
            med = _median(sizes)
            max_size = max(sizes) if sizes else 0.0
            ratio = max_size / med if med > 0 else 0.0
            score = _score_ratio(ratio)

            sum_bid = sum(float(s) for _, s in bids if s is not None)
            sum_ask = sum(float(s) for _, s in asks if s is not None)
            total = sum_bid + sum_ask
            imbalance_pct = (sum_bid - sum_ask) / total * 100.0 if total > 0 else 0.0

            # boost score if recent iceberg/wall events exist
            raw_events = await r.lrange(events_key, -50, -1)
            now = int(time.time() * 1000)
            for e in raw_events or []:
                try:
                    ev = json.loads(e)
                except json.JSONDecodeError:
                    continue
                ts = int(ev.get("ts", ev.get("ts_start", 0)))
                if now - ts > EVENT_LOOKBACK_MS:
                    continue
                if "ICEBERG" in ev.get("type", "") or "WALL" in ev.get("type", ""):
                    score = min(6.0, score + 1.0)
                    break

            ts_snap = int(snap.get("ts", now))
            out = {
                "exchange": exchange,
                "symbol": symbol,
                "ts": ts_snap,
                "score_orderbook": round(score, 3),
                "max_size_ratio": round(ratio, 3),
                "imbalance_pct": round(imbalance_pct, 2),
                "sum_bid": round(sum_bid, 4),
                "sum_ask": round(sum_ask, 4),
            }
            key_score = REDIS_KEY_SCORE_ORDERBOOK.format(exchange=exchange, symbol=symbol)
            key_imbalance = REDIS_KEY_IMBALANCE.format(exchange=exchange, symbol=symbol)
            key_history = REDIS_KEY_IMBALANCE_HISTORY.format(exchange=exchange, symbol=symbol)
            await r.set(key_score, json.dumps(out), ex=300)
            await r.set(key_imbalance, json.dumps({"ts": ts_snap, "imbalance_pct": round(imbalance_pct, 2)}), ex=300)
            await r.rpush(key_history, json.dumps({"ts": ts_snap, "imbalance_pct": round(imbalance_pct, 2)}))
            await r.ltrim(key_history, -IMBALANCE_HISTORY_MAXLEN, -1)
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[feature_orderbook] Error: {e}")
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379")
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()
    asyncio.run(run_feature_engine_orderbook(args.redis, args.exchange, args.symbol))


if __name__ == "__main__":
    main()
