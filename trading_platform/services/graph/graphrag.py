"""
GraphRAG: query graph for similar situations (price move + OI + liquidations) for AI context.
"""
import os
from typing import Any

NEO4J_URI = os.environ.get("NEO4J_URI", "")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")


def _driver():
    if not NEO4J_URI or not NEO4J_PASSWORD:
        return None
    try:
        from neo4j import GraphDatabase
        return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    except ImportError:
        return None


def query_similar_situations(
    exchange: str,
    symbol: str,
    price_delta_hint: str = "up",
    oi_delta_hint: str = "any",
    liquidation_side_hint: str | None = None,
    limit: int = 10,
) -> str:
    """
    Find past situations with similar hints (e.g. price up + OI down + short liquidation).
    Returns a text summary for Gemini context, or empty string if no graph.
    """
    d = _driver()
    if not d:
        return ""
    try:
        with d.session() as session:
            result = session.run(
                """
                MATCH (e:Event)-[:PRECEDES]->(m:MarketState)
                WHERE m.exchange = $exchange AND m.symbol = $symbol
                RETURN e.type AS eventType, e.ts AS ts, m.price AS price, m.oi AS oi
                ORDER BY e.ts DESC
                LIMIT $limit
                """,
                exchange=exchange,
                symbol=symbol,
                limit=limit,
            )
            rows = list(result)
        if not rows:
            return ""
        lines = [
            f"Past events for {exchange}/{symbol}: " + "; ".join(
                f"{r['eventType']} @ {r['ts']} (price={r['price']}, oi={r['oi']})" for r in rows
            )
        ]
        return "\n".join(lines)
    except Exception:
        return ""
    finally:
        d.close()
