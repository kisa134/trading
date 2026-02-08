"""
Experience Replay: store successful predictions for few-shot retrieval.
Uses PostgreSQL ai_experience table. Optional pgvector: pass embedding at add_experience
and query_embedding at search_few_shot for similarity-based retrieval; else time-based.
"""
import os
import sys
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

COLD_STORAGE_URL = os.environ.get("COLD_STORAGE_URL", "")


def _register_pgvector(conn):
    """Register pgvector type with asyncpg if available."""
    try:
        from pgvector.asyncpg import register_vector
        register_vector(conn)
        return True
    except ImportError:
        return False


async def add_experience(
    prediction_id: str,
    exchange: str,
    symbol: str,
    outcome: str,
    summary_text: str,
    embedding: list[float] | None = None,
) -> bool:
    """Insert one experience row (call when outcome is success or after reflection).
    If embedding is provided and ai_experience.embedding column exists (pgvector), store it."""
    if not COLD_STORAGE_URL:
        return False
    try:
        import asyncpg
        conn = await asyncpg.connect(COLD_STORAGE_URL)
        try:
            if embedding is not None:
                try:
                    _register_pgvector(conn)
                    await conn.execute(
                        """
                        INSERT INTO ai_experience (prediction_id, exchange, symbol, outcome, summary_text, embedding)
                        VALUES ($1, $2, $3, $4, $5, $6::vector)
                        """,
                        prediction_id,
                        exchange,
                        symbol,
                        outcome,
                        summary_text,
                        embedding,
                    )
                    return True
                except Exception:
                    pass
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


async def search_few_shot(
    exchange: str,
    symbol: str,
    limit: int = 5,
    query_embedding: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Return few-shot examples: by similarity to query_embedding if provided and pgvector available, else last N by time."""
    if not COLD_STORAGE_URL:
        return []
    try:
        import asyncpg
        conn = await asyncpg.connect(COLD_STORAGE_URL)
        try:
            if query_embedding is not None:
                try:
                    _register_pgvector(conn)
                    rows = await conn.fetch(
                        """
                        SELECT id, prediction_id, outcome, summary_text, created_at
                        FROM ai_experience
                        WHERE exchange = $1 AND symbol = $2 AND outcome = 'success' AND embedding IS NOT NULL
                        ORDER BY embedding <=> $3::vector
                        LIMIT $4
                        """,
                        exchange,
                        symbol,
                        query_embedding,
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
                except Exception:
                    pass
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
