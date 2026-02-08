"""
Experience Replay: store successful predictions for few-shot retrieval.
Uses PostgreSQL ai_experience table; optional pgvector later for similarity search.
"""
import os
import sys
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

COLD_STORAGE_URL = os.environ.get("COLD_STORAGE_URL", "")


async def add_experience(
    prediction_id: str,
    exchange: str,
    symbol: str,
    outcome: str,
    summary_text: str,
) -> bool:
    """Insert one experience row (call when outcome is success or after reflection)."""
    if not COLD_STORAGE_URL:
        return False
    try:
        import asyncpg
        conn = await asyncpg.connect(COLD_STORAGE_URL)
        try:
            await conn.execute(
                """
                INSERT INTO ai_experience (prediction_id, exchange, symbol, outcome, summary_text)
                VALUES ($1, $2, $3, $4, $5)
                """,
                prediction_id,
                exchange,
                symbol,
                outcome,
                summary_text,
            )
            return True
        finally:
            await conn.close()
    except Exception as e:
        print(f"[experience_replay] add_experience: {e}")
        return False


async def search_few_shot(exchange: str, symbol: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return last N successful experiences for (exchange, symbol) as few-shot examples."""
    if not COLD_STORAGE_URL:
        return []
    try:
        import asyncpg
        conn = await asyncpg.connect(COLD_STORAGE_URL)
        try:
            rows = await conn.fetch(
                """
                SELECT id, prediction_id, outcome, summary_text, created_at
                FROM ai_experience
                WHERE exchange = $1 AND symbol = $2 AND outcome = 'success'
                ORDER BY created_at DESC
                LIMIT $3
                """,
                exchange,
                symbol,
                limit,
            )
            return [
                {
                    "id": str(r["id"]),
                    "prediction_id": str(r["prediction_id"]),
                    "outcome": r["outcome"],
                    "summary_text": r["summary_text"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in rows
            ]
        finally:
            await conn.close()
    except Exception as e:
        print(f"[experience_replay] search_few_shot: {e}")
        return []
