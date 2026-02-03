"""
Rule-based trend reversal probability engine.
Consumes TrendPower/Delta and Exhaustion/Absorption scores.
Publishes to signals.rule_reversal stream and Redis list.
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
    STREAM_SIGNALS_RULE_REVERSAL,
    REDIS_KEY_SCORES_TREND,
    REDIS_KEY_SCORES_EXHAUSTION,
    REDIS_KEY_SIGNALS_RULE,
    SIGNALS_MAXLEN,
)

TREND_STRONG = 250.0
EXH_THRESHOLD = 60.0
ABS_THRESHOLD = 60.0
HORIZON_BARS = 8


async def run_rule_reversal_engine(redis_url: str, exchange: str, symbol: str):
    r = redis.from_url(redis_url, decode_responses=True)
    key_trend = REDIS_KEY_SCORES_TREND.format(exchange=exchange, symbol=symbol)
    key_exh = REDIS_KEY_SCORES_EXHAUSTION.format(exchange=exchange, symbol=symbol)
    key_signals = REDIS_KEY_SIGNALS_RULE.format(exchange=exchange, symbol=symbol)

    while True:
        try:
            trend_items = await r.lrange(key_trend, -5, -1)
            if not trend_items:
                await asyncio.sleep(1)
                continue
            trends = []
            for x in trend_items:
                try:
                    trends.append(json.loads(x))
                except json.JSONDecodeError:
                    pass
            if not trends:
                await asyncio.sleep(1)
                continue
            latest = trends[-1]
            trend_power = float(latest.get("trend_power", 0))
            deltas = [float(t.get("trend_power_delta", 0)) for t in trends]
            decel = sum(1 for d in deltas[-3:] if d < 0) >= 2

            exh_raw = await r.lrange(key_exh, -1, -1)
            if exh_raw:
                try:
                    exh = json.loads(exh_raw[0])
                except json.JSONDecodeError:
                    exh = {}
            else:
                exh = {}
            exhaustion = float(exh.get("exhaustion_score", 0))
            absorption = float(exh.get("absorption_score", 0))

            prob = 0.05
            if abs(trend_power) >= TREND_STRONG and decel:
                prob = 0.4
            if (exhaustion >= EXH_THRESHOLD or absorption >= ABS_THRESHOLD) and abs(trend_power) >= TREND_STRONG and decel:
                prob = 0.65
            if (exhaustion >= EXH_THRESHOLD and absorption >= ABS_THRESHOLD) and abs(trend_power) >= TREND_STRONG and decel:
                prob = 0.8

            expected_move = round(max(0.1, abs(trend_power) / 100.0), 3)
            out = {
                "exchange": exchange,
                "symbol": symbol,
                "ts": int(latest.get("ts", time.time() * 1000)),
                "prob_reversal_rule": round(prob, 3),
                "reversal_horizon_bars": HORIZON_BARS,
                "expected_move_range": [round(expected_move * 0.5, 3), expected_move],
            }
            payload = json.dumps(out)
            await r.xadd(STREAM_SIGNALS_RULE_REVERSAL, {"payload": payload}, maxlen=10000)
            await r.rpush(key_signals, payload)
            await r.ltrim(key_signals, -SIGNALS_MAXLEN, -1)
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[rule_reversal] Error: {e}")
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379")
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--symbol", default="BTCUSDT")
    args = parser.parse_args()
    asyncio.run(run_rule_reversal_engine(args.redis, args.exchange, args.symbol))


if __name__ == "__main__":
    main()
