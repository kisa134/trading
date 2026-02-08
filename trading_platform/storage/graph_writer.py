"""
Graph writer worker: reads from Redis Streams (events, liquidations, open_interest),
writes Event and MarketState nodes to Neo4j. Periodically samples PriceLevel and Trade from DOM/trades.
"""
import asyncio
import json
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import redis.asyncio as redis

from shared.streams import (
    STREAM_EVENTS,
    STREAM_LIQUIDATIONS,
    STREAM_OPEN_INTEREST,
    REDIS_KEY_TRADES,
    REDIS_KEY_DOM,
)

SAMPLE_INTERVAL = float(os.environ.get("GRAPH_SAMPLE_INTERVAL_SEC", "45"))
TRADE_MIN_SIZE = float(os.environ.get("GRAPH_TRADE_MIN_SIZE", "0.01"))
PRICE_LEVEL_TOP_N = int(os.environ.get("GRAPH_PRICE_LEVEL_TOP_N", "5"))
GRAPH_SAMPLE_PAIRS = os.environ.get("GRAPH_SAMPLE_PAIRS", "bybit:BTCUSDT")


async def get_last_price(r: redis.Redis, exchange: str, symbol: str) -> float | None:
    """Read last trade price from Redis list."""
    key = REDIS_KEY_TRADES.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(key, -1, -1)
    if not items:
        return None
    try:
        t = json.loads(items[0])
        return float(t.get("price", 0)) if t.get("price") else None
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def _parse_dom_bids_asks(raw: str | None):
    """Return (bids, asks, ts) from DOM JSON. Bids/asks are list of [price, size]."""
    if not raw:
        return [], [], 0
    try:
        data = json.loads(raw)
        ts = int(data.get("ts", 0))
        bids = data.get("bids") or []
        asks = data.get("asks") or []
        return bids, asks, ts
    except (json.JSONDecodeError, TypeError, KeyError):
        return [], [], 0


async def _sample_price_levels_and_trades(r: redis.Redis, pairs: list[tuple[str, str]]) -> None:
    """For each (exchange, symbol) write top PriceLevels from DOM and last large Trade to Neo4j."""
    try:
        from services.graph.writer import write_price_level, write_trade
    except ImportError:
        return
    now_ts = int(time.time() * 1000)
    for exchange, symbol in pairs:
        try:
            dom_key = REDIS_KEY_DOM.format(exchange=exchange, symbol=symbol)
            raw = await r.get(dom_key)
            bids, asks, ts = _parse_dom_bids_asks(raw)
            ts = ts or now_ts
            for i, entry in enumerate(bids[:PRICE_LEVEL_TOP_N]):
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    price = float(entry[0])
                    vol = float(entry[1])
                    write_price_level(exchange, symbol, price, ts, vol_bid=vol, vol_ask=0.0)
            for i, entry in enumerate(asks[:PRICE_LEVEL_TOP_N]):
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    price = float(entry[0])
                    vol = float(entry[1])
                    write_price_level(exchange, symbol, price, ts, vol_bid=0.0, vol_ask=vol)

            trades_key = REDIS_KEY_TRADES.format(exchange=exchange, symbol=symbol)
            items = await r.lrange(trades_key, -1, -1)
            if items:
                try:
                    t = json.loads(items[0])
                    size = float(t.get("size", t.get("volume", 0)))
                    if size >= TRADE_MIN_SIZE:
                        price = float(t.get("price", 0))
                        side = str(t.get("side", ""))
                        ts_t = int(t.get("ts", 0))
                        trade_id = f"{exchange}:{symbol}:{ts_t}:{price}:{size}:{side}"
                        write_trade(exchange, symbol, trade_id, ts_t, price, size, side)
                except (json.JSONDecodeError, TypeError, KeyError):
                    pass
        except Exception as e:
            print(f"[graph_writer] sample error for {exchange}/{symbol}: {e}")


async def run_graph_writer(redis_url: str):
    r = redis.from_url(redis_url, decode_responses=True)
    last_ids = {
        STREAM_EVENTS: "$",
        STREAM_LIQUIDATIONS: "$",
        STREAM_OPEN_INTEREST: "$",
    }
    # (exchange, symbol) -> (ts, oi) for MarketState
    last_oi: dict[tuple[str, str], tuple[int, float]] = {}
    market_state_interval = 5.0
    last_market_state_flush = 0.0
    last_sample_time = 0.0
    sample_pairs: list[tuple[str, str]] = []
    for part in GRAPH_SAMPLE_PAIRS.strip().split(","):
        part = part.strip()
        if ":" in part:
            ex, sym = part.split(":", 1)
            sample_pairs.append((ex.strip(), sym.strip()))

    from services.graph.writer import write_event, write_market_state

    while True:
        try:
            streams = [[name, last_ids[name]] for name in last_ids]
            result = await r.xread(streams=dict(streams), count=100, block=2000)
            if result:
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
                        if not exchange or not symbol:
                            continue

                        if stream_name == STREAM_EVENTS:
                            event_type = payload.get("type", "event")
                            ts = int(payload.get("ts_start") or payload.get("ts") or 0)
                            write_event(exchange, symbol, event_type, ts, payload)
                            price = await get_last_price(r, exchange, symbol)
                            oi_data = last_oi.get((exchange, symbol))
                            oi = oi_data[1] if oi_data else None
                            write_market_state(exchange, symbol, ts, price or 0.0, oi)

                        elif stream_name == STREAM_LIQUIDATIONS:
                            ts = int(payload.get("ts", 0))
                            liq_payload = {
                                "price": payload.get("price"),
                                "quantity": payload.get("quantity"),
                                "side": payload.get("side"),
                            }
                            write_event(exchange, symbol, "liquidation", ts, liq_payload)
                            price = float(payload.get("price", 0)) or (await get_last_price(r, exchange, symbol))
                            oi_data = last_oi.get((exchange, symbol))
                            oi = oi_data[1] if oi_data else None
                            write_market_state(exchange, symbol, ts, price or 0.0, oi)

                        elif stream_name == STREAM_OPEN_INTEREST:
                            ts = int(payload.get("ts", 0))
                            oi = float(payload.get("open_interest", 0) or 0)
                            last_oi[(exchange, symbol)] = (ts, oi)

            # Periodic MarketState flush for pairs we have OI for (price from trades)
            now = time.time()
            if now - last_market_state_flush >= market_state_interval and last_oi:
                for (exchange, symbol), (ts, oi) in list(last_oi.items()):
                    price = await get_last_price(r, exchange, symbol)
                    if price is not None:
                        write_market_state(exchange, symbol, ts, price, oi)
                last_market_state_flush = now

            # Periodic PriceLevel and Trade sampling for configured pairs
            if sample_pairs and now - last_sample_time >= SAMPLE_INTERVAL:
                await _sample_price_levels_and_trades(r, sample_pairs)
                last_sample_time = now

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[graph_writer] Error: {e}")
            await asyncio.sleep(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis", default=os.environ.get("REDIS_URL", "redis://localhost:6379"))
    args = parser.parse_args()
    asyncio.run(run_graph_writer(args.redis))


if __name__ == "__main__":
    main()
