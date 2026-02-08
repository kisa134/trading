"""
Prediction Store: persist AI predictions to Redis (hot) and TimescaleDB (cold).
"""
import json
import uuid
import os
import sys
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from shared.streams import REDIS_KEY_AI_PREDICTIONS_LIST, AI_PREDICTIONS_MAXLEN


def _cold_url() -> str:
    return os.environ.get("COLD_STORAGE_URL", "")


async def save_prediction(
    redis_client,
    exchange: str,
    symbol: str,
    ts_prediction: int,
    horizon_minutes: int,
    price_at_prediction: float,
    *,
    target_price: float | None = None,
    direction: str | None = None,
    expected_range_low: float | None = None,
    expected_range_high: float | None = None,
    snapshot_ref: str | None = None,
    context_snapshot: dict | None = None,
    models_used: list[str] | dict | None = None,
) -> str:
    """Save prediction to Redis and optionally to TimescaleDB. Returns prediction UUID hex."""
    prediction_id = uuid.uuid4()
    row = {
        "id": str(prediction_id),
        "exchange": exchange,
        "symbol": symbol,
        "ts_prediction": ts_prediction,
        "horizon_minutes": horizon_minutes,
        "price_at_prediction": price_at_prediction,
        "target_price": target_price,
        "direction": direction,
        "expected_range_low": expected_range_low,
        "expected_range_high": expected_range_high,
        "snapshot_ref": snapshot_ref,
        "context_snapshot": context_snapshot,
        "models_used": models_used,
    }
    key = REDIS_KEY_AI_PREDICTIONS_LIST.format(exchange=exchange, symbol=symbol)
    await redis_client.rpush(key, json.dumps(row))
    await redis_client.ltrim(key, -AI_PREDICTIONS_MAXLEN, -1)

    cold = _cold_url()
    if cold:
        try:
            import asyncpg
            conn = await asyncpg.connect(cold)
            try:
                await conn.execute(
                    """
                    INSERT INTO ai_predictions (
                        id, exchange, symbol, ts_prediction, horizon_minutes,
                        price_at_prediction, target_price, direction,
                        expected_range_low, expected_range_high,
                        snapshot_ref, context_snapshot, models_used
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    """,
                    prediction_id,
                    exchange,
                    symbol,
                    ts_prediction,
                    horizon_minutes,
                    price_at_prediction,
                    target_price,
                    direction,
                    expected_range_low,
                    expected_range_high,
                    snapshot_ref,
                    json.dumps(context_snapshot) if context_snapshot else None,
                    json.dumps(models_used) if models_used else None,
                )
            finally:
                await conn.close()
        except Exception as e:
            print(f"[prediction_store] cold write failed: {e}")

    return prediction_id.hex
