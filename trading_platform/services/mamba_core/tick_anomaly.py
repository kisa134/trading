"""
Tick anomaly detector: consumes trades from Redis, emits volume/delta anomalies and Mamba signal.
Uses Tick Encoder (LSTM CPU or Mamba when available) for prob_up/prob_down/delta_score.
Writes to STREAM_AI_MAMBA_ANOMALIES, REDIS_KEY_AI_ANOMALIES, STREAM_MAMBA_SIGNAL, REDIS_KEY_MAMBA_SIGNAL.
"""
import asyncio
import json
import argparse
import sys
import os
from collections import deque

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import redis.asyncio as redis

from shared.streams import (
    STREAM_TRADES,
    STREAM_AI_MAMBA_ANOMALIES,
    STREAM_MAMBA_SIGNAL,
    REDIS_KEY_AI_ANOMALIES,
    REDIS_KEY_MAMBA_SIGNAL,
    MAMBA_SIGNAL_TTL_SEC,
)


ROLLING_WINDOW = 100
SIGNAL_WINDOW = 64
SIGNAL_EVERY_N_TICKS = 20
VOLUME_SPIKE_MULT = 2.5
ANOMALY_TTL_SEC = 60


async def run_tick_anomaly_worker(redis_url: str, exchange_filter: str = "", symbol_filter: str = ""):
    r = redis.from_url(redis_url, decode_responses=True)
    last_id = "$"
    recent: dict[tuple[str, str], deque] = {}
    tick_count: dict[tuple[str, str], int] = {}
    encoder = None
    try:
        from services.mamba_core.models import build_tick_encoder, infer_signal
        encoder = build_tick_encoder(use_mamba=False)
    except Exception:
        pass

    while True:
        try:
            result = await r.xread({STREAM_TRADES: last_id}, count=50, block=1000)
            if not result:
                continue
            for _stream, messages in result:
                for msg_id, fields in messages:
                    last_id = msg_id
                    payload_str = (fields or {}).get("payload")
                    if not payload_str:
                        continue
                    try:
                        t = json.loads(payload_str)
                    except json.JSONDecodeError:
                        continue
                    exchange = t.get("exchange", "")
                    symbol = t.get("symbol", "")
                    if exchange_filter and exchange != exchange_filter:
                        continue
                    if symbol_filter and symbol != symbol_filter:
                        continue
                    key = (exchange, symbol)
                    if key not in recent:
                        recent[key] = deque(maxlen=max(ROLLING_WINDOW, SIGNAL_WINDOW))
                        tick_count[key] = 0
                    side = (t.get("side") or "").lower()
                    price = float(t.get("price", 0))
                    size = float(t.get("size", t.get("volume", 0)))
                    ts = int(t.get("ts", 0))
                    recent[key].append({"ts": ts, "side": side, "price": price, "size": size})
                    tick_count[key] += 1

                    vol_list = [x["size"] for x in recent[key]]
                    avg_vol = sum(vol_list) / len(vol_list) if vol_list else size
                    if avg_vol <= 0:
                        continue
                    if size >= avg_vol * VOLUME_SPIKE_MULT:
                        anomaly = {
                            "exchange": exchange,
                            "symbol": symbol,
                            "ts": ts,
                            "type": "volume_spike",
                            "price": price,
                            "size": size,
                            "side": side,
                            "avg_vol": round(avg_vol, 4),
                            "ratio": round(size / avg_vol, 2),
                        }
                        await r.xadd(
                            STREAM_AI_MAMBA_ANOMALIES,
                            {"payload": json.dumps(anomaly)},
                            maxlen=5000,
                        )
                        anomalies_key = REDIS_KEY_AI_ANOMALIES.format(exchange=exchange, symbol=symbol)
                        await r.set(anomalies_key, json.dumps(anomaly), ex=ANOMALY_TTL_SEC)

                    if tick_count[key] % SIGNAL_EVERY_N_TICKS == 0 and len(recent[key]) >= SIGNAL_WINDOW:
                        try:
                            from services.mamba_core.models import infer_signal
                            ticks_list = list(recent[key])
                            signal = infer_signal(encoder, ticks_list, window=SIGNAL_WINDOW)
                            signal["exchange"] = exchange
                            signal["symbol"] = symbol
                            payload = json.dumps(signal)
                            await r.xadd(STREAM_MAMBA_SIGNAL, {"payload": payload}, maxlen=5000)
                            sig_key = REDIS_KEY_MAMBA_SIGNAL.format(exchange=exchange, symbol=symbol)
                            await r.set(sig_key, payload, ex=MAMBA_SIGNAL_TTL_SEC)
                        except Exception:
                            pass
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[tick_anomaly] {e}")
            await asyncio.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default="redis://localhost:6379")
    parser.add_argument("--exchange", default="", help="Filter by exchange")
    parser.add_argument("--symbol", default="", help="Filter by symbol")
    args = parser.parse_args()
    asyncio.run(run_tick_anomaly_worker(args.redis, args.exchange, args.symbol))


if __name__ == "__main__":
    main()
