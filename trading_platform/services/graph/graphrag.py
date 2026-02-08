"""
GraphRAG: query graph for similar situations (price move + OI + liquidations) for AI context.
Multi-hop: filter by event type, time window; optionally include Prediction/Outcome subgraphs.
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
    event_type: str | None = None,
    ts_since: int | None = None,
    include_outcomes: bool = True,
) -> str:
    """
    Find past situations (Event -> MarketState) with optional filters.
    event_type: filter by Event.type (e.g. "liquidation", "iceberg", "wall").
    ts_since: only events with MarketState.ts >= ts_since (ms).
    include_outcomes: if True, include Prediction/Outcome when present for richer context.
    Returns a text summary for Gemini context, or empty string if no graph.
    """
    d = _driver()
    if not d:
        return ""
    try:
        with d.session() as session:
            # Base: Event -PRECEDES-> MarketState
            where_clauses = ["m.exchange = $exchange", "m.symbol = $symbol"]
            params: dict[str, Any] = {"exchange": exchange, "symbol": symbol, "limit": limit}
            if event_type:
                where_clauses.append("e.type = $event_type")
                params["event_type"] = event_type
            if ts_since is not None:
                where_clauses.append("m.ts >= $ts_since")
                params["ts_since"] = ts_since
            where_str = " AND ".join(where_clauses)

            if include_outcomes:
                # Optional subgraph: (e)-[:PRECEDES]->(m)<-[:ABOUT]-(p:Prediction)<-[:EVALUATES]-(o:Outcome)
                result = session.run(
                    f"""
                    MATCH (e:Event)-[:PRECEDES]->(m:MarketState)
                    WHERE {where_str}
                    OPTIONAL MATCH (p:Prediction)-[:ABOUT]->(m)
                    OPTIONAL MATCH (o:Outcome)-[:EVALUATES]->(p)
                    RETURN e.type AS eventType, e.ts AS ts, m.price AS price, m.oi AS oi,
                           p.id AS predId, o.outcome AS outcome, o.actual_price AS actualPrice
                    ORDER BY e.ts DESC
                    LIMIT $limit
                    """,
                    **params,
                )
                rows = list(result)
                if not rows:
                    return ""
                lines = []
                for r in rows:
                    parts = [f"{r['eventType']} @ {r['ts']} (price={r['price']}, oi={r['oi']})"]
                    if r.get("outcome"):
                        parts.append(f" -> outcome={r['outcome']} actual={r['actualPrice']}")
                    lines.append("; ".join(parts))
                return f"Past events for {exchange}/{symbol}:\n" + "\n".join(lines)
            else:
                result = session.run(
                    f"""
                    MATCH (e:Event)-[:PRECEDES]->(m:MarketState)
                    WHERE {where_str}
                    RETURN e.type AS eventType, e.ts AS ts, m.price AS price, m.oi AS oi
                    ORDER BY e.ts DESC
                    LIMIT $limit
                    """,
                    **params,
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


def query_by_price_level(
    exchange: str,
    symbol: str,
    price: float,
    tolerance_pct: float = 0.001,
    limit: int = 10,
    ts_since: int | None = None,
) -> str:
    """
    Anchor retraction: find events and market states near this price level.
    tolerance_pct: relative price band (e.g. 0.001 = 0.1%).
    """
    d = _driver()
    if not d:
        return ""
    try:
        lo = price * (1 - tolerance_pct)
        hi = price * (1 + tolerance_pct)
        params: dict[str, Any] = {"exchange": exchange, "symbol": symbol, "lo": lo, "hi": hi, "limit": limit}
        if ts_since is not None:
            params["ts_since"] = ts_since
        where_ts = " AND m.ts >= $ts_since" if ts_since is not None else ""
        with d.session() as session:
            result = session.run(
                f"""
                MATCH (e:Event)-[:PRECEDES]->(m:MarketState)
                WHERE m.exchange = $exchange AND m.symbol = $symbol
                  AND m.price >= $lo AND m.price <= $hi
                  {where_ts}
                RETURN e.type AS eventType, e.ts AS ts, m.price AS price
                ORDER BY e.ts DESC
                LIMIT $limit
                """,
                **params,
            )
            rows = list(result)
        if not rows:
            return ""
        return f"Events near price {price} for {exchange}/{symbol}:\n" + "\n".join(
            f"{r['eventType']} @ {r['ts']} price={r['price']}" for r in rows
        )
    except Exception:
        return ""
    finally:
        d.close()


def query_chain_events_to_price(
    exchange: str,
    symbol: str,
    limit: int = 5,
    ts_since: int | None = None,
) -> str:
    """
    Multi-hop: Event -> MarketState chains.
    Returns a short summary (e.g. event type -> resulting price).
    """
    d = _driver()
    if not d:
        return ""
    try:
        params: dict[str, Any] = {"exchange": exchange, "symbol": symbol, "limit": limit}
        if ts_since is not None:
            params["ts_since"] = ts_since
        where_ts = " AND e.ts >= $ts_since" if ts_since is not None else ""
        with d.session() as session:
            result = session.run(
                f"""
                MATCH (e:Event)-[:PRECEDES]->(m:MarketState)
                WHERE e.exchange = $exchange AND e.symbol = $symbol
                  {where_ts}
                RETURN e.type AS eventType, e.ts AS ts, m.price AS price
                ORDER BY e.ts DESC
                LIMIT $limit
                """,
                **params,
            )
            rows = list(result)
        if not rows:
            return ""
        return f"Event->State chains for {exchange}/{symbol}:\n" + "\n".join(
            f"{r['eventType']} @ {r['ts']} -> price={r['price']}" for r in rows
        )
    except Exception:
        return ""
    finally:
        d.close()
