"""
Celery tasks: evaluate_outcomes (periodic), run_self_reflection (on failed prediction).
"""
import asyncio
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from celery_app import app
from shared.streams import REDIS_KEY_TRADES, STREAM_KLINE

COLD_STORAGE_URL = os.environ.get("COLD_STORAGE_URL", "")


def _sync_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.task(bind=True, name="services.ai.tasks.evaluate_outcomes")
def evaluate_outcomes(self):
    """Periodic: fetch predictions with null outcome and past horizon, compute outcome from Redis/TimescaleDB."""
    return _sync_async(_evaluate_outcomes_async())


async def _evaluate_outcomes_async():
    if not COLD_STORAGE_URL:
        return {"ok": 0, "reason": "no cold storage"}
    try:
        import redis.asyncio as redis
        import asyncpg
    except ImportError:
        return {"ok": 0, "reason": "redis or asyncpg not installed"}
    r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
    conn = await asyncpg.connect(COLD_STORAGE_URL)
    try:
        rows = await conn.fetch(
            """
            SELECT id, exchange, symbol, ts_prediction, horizon_minutes, price_at_prediction,
                   target_price, direction, expected_range_low, expected_range_high
            FROM ai_predictions
            WHERE outcome IS NULL
              AND (ts_prediction + horizon_minutes * 60000) < $1
            LIMIT 100
            """,
            __import__("time").time() * 1000,
        )
        updated = 0
        for row in rows:
            pred_id = row["id"]
            exchange = row["exchange"]
            symbol = row["symbol"]
            ts_end = row["ts_prediction"] + row["horizon_minutes"] * 60 * 1000
            target = row["target_price"]
            direction = row["direction"]
            range_low = row["expected_range_low"]
            range_high = row["expected_range_high"]
            price_at = row["price_at_prediction"]
            actual_price = await _get_actual_price(r, conn, exchange, symbol, ts_end)
            if actual_price is None:
                continue
            outcome = _compute_outcome(
                price_at=price_at,
                actual_price=actual_price,
                target_price=target,
                direction=direction,
                expected_range_low=range_low,
                expected_range_high=range_high,
            )
            await conn.execute(
                """
                UPDATE ai_predictions SET outcome = $1, outcome_ts = $2, actual_price = $3
                WHERE id = $4
                """,
                outcome,
                int(__import__("time").time() * 1000),
                actual_price,
                pred_id,
            )
            updated += 1
            if outcome == "fail":
                run_self_reflection.delay(str(pred_id))
            elif outcome == "success":
                from services.ai.experience_replay import add_experience
                summary = f"Price at prediction: {price_at}. Actual: {actual_price}. Direction: {direction or 'n/a'}."
                await add_experience(str(pred_id), exchange, symbol, "success", summary)
            try:
                from services.graph.writer import write_outcome
                if outcome == "success":
                    write_outcome(str(pred_id), outcome, actual_price, None)
            except Exception:
                pass
        return {"ok": 1, "updated": updated}
    finally:
        await conn.close()
        await r.aclose()


def _compute_outcome(
    price_at: float,
    actual_price: float,
    target_price: float | None,
    direction: str | None,
    expected_range_low: float | None,
    expected_range_high: float | None,
) -> str:
    if target_price is not None:
        hit = abs(actual_price - target_price) / max(target_price, 1e-9) < 0.005
        return "success" if hit else "fail"
    if direction and direction.lower() in ("up", "long", "buy"):
        return "success" if actual_price > price_at else "fail"
    if direction and direction.lower() in ("down", "short", "sell"):
        return "success" if actual_price < price_at else "fail"
    if expected_range_low is not None and expected_range_high is not None:
        in_range = expected_range_low <= actual_price <= expected_range_high
        return "success" if in_range else "fail"
    return "fail"


async def _get_actual_price(r, conn, exchange: str, symbol: str, ts_end: int) -> float | None:
    """Prefer close price at ts_end from kline/trades."""
    trades_key = REDIS_KEY_TRADES.format(exchange=exchange, symbol=symbol)
    items = await r.lrange(trades_key, -500, -1)
    if items:
        for raw in reversed(items):
            try:
                t = json.loads(raw)
                if int(t.get("ts", 0)) >= ts_end - 60000:
                    return float(t.get("price", 0))
            except (json.JSONDecodeError, TypeError):
                continue
    try:
        row = await conn.fetchrow(
            "SELECT price FROM trades WHERE exchange = $1 AND symbol = $2 AND ts <= $3 ORDER BY ts DESC LIMIT 1",
            exchange, symbol, ts_end + 60000,
        )
        if row:
            return float(row["price"])
    except Exception:
        pass
    return None


@app.task(bind=True, name="services.ai.tasks.refresh_gemini_cache")
def refresh_gemini_cache(self):
    """Clear Redis cache name so next Gemini request recreates cached content (TTL refresh)."""
    import redis
    r = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
    from services.ai.context_caching import REDIS_KEY_GEMINI_CACHE_NAME
    r.delete(REDIS_KEY_GEMINI_CACHE_NAME)
    return {"ok": 1}


@app.task(bind=True, name="services.ai.tasks.run_self_reflection")
def run_self_reflection(self, prediction_id: str):
    """Call DeepSeek R1 for failed prediction, save to ai_reflections."""
    return _sync_async(_run_self_reflection_async(prediction_id))


async def _run_self_reflection_async(prediction_id: str):
    if not COLD_STORAGE_URL:
        return {"ok": 0}
    try:
        import asyncpg
        from services.ai.router import route_reflection
    except ImportError:
        return {"ok": 0}
    conn = await asyncpg.connect(COLD_STORAGE_URL)
    try:
        row = await conn.fetchrow(
            "SELECT exchange, symbol, ts_prediction, price_at_prediction, target_price, direction, "
            "expected_range_low, expected_range_high, actual_price, outcome FROM ai_predictions WHERE id = $1",
            prediction_id,
        )
        if not row or row["outcome"] != "fail":
            return {"ok": 0}
        prompt = (
            f"Prediction for {row['exchange']} {row['symbol']}: at ts={row['ts_prediction']} "
            f"price was {row['price_at_prediction']}, target={row['target_price']}, direction={row['direction']}, "
            f"expected range [{row['expected_range_low']}, {row['expected_range_high']}]. "
            f"Actual outcome: price={row['actual_price']}. Why did this prediction fail? What was missed?"
        )
        reflection_text = await route_reflection(prompt)
        if reflection_text:
            await conn.execute(
                "INSERT INTO ai_reflections (prediction_id, reflection_text, model_used) VALUES ($1, $2, $3)",
                prediction_id,
                reflection_text,
                "deepseek-r1",
            )
        try:
            from services.graph.writer import write_outcome
            write_outcome(prediction_id, "fail", float(row["actual_price"]), reflection_text)
        except Exception:
            pass
        return {"ok": 1}
    finally:
        await conn.close()
