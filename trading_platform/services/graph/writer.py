"""
Write events and outcomes to graph (Neo4j). No-op if NEO4J_URI not set.
Extended: PriceLevel, Trade, StrategyOutcome; FOLLOWED_BY, REJECTED_AT.
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


def write_event(exchange: str, symbol: str, event_type: str, ts: int, payload: dict[str, Any]) -> bool:
    """Create Event node and link to latest MarketState. Returns True if written."""
    d = _driver()
    if not d:
        return False
    try:
        with d.session() as session:
            session.run(
                """
                MERGE (e:Event {id: $id})
                SET e.exchange = $exchange, e.symbol = $symbol, e.type = $type, e.ts = $ts, e.payload = $payload
                WITH e
                OPTIONAL MATCH (m:MarketState {exchange: $exchange, symbol: $symbol})
                WHERE m.ts <= $ts
                WITH e, m ORDER BY m.ts DESC LIMIT 1
                WHERE m IS NOT NULL
                MERGE (e)-[:PRECEDES]->(m)
                """,
                id=f"{exchange}:{symbol}:{event_type}:{ts}",
                exchange=exchange,
                symbol=symbol,
                type=event_type,
                ts=ts,
                payload=str(payload),
            )
        return True
    except Exception:
        return False
    finally:
        d.close()


def write_market_state(exchange: str, symbol: str, ts: int, price: float, oi: float | None = None) -> bool:
    """Create or update MarketState node."""
    d = _driver()
    if not d:
        return False
    try:
        with d.session() as session:
            session.run(
                """
                MERGE (m:MarketState {id: $id})
                SET m.exchange = $exchange, m.symbol = $symbol, m.ts = $ts, m.price = $price, m.oi = $oi
                """,
                id=f"{exchange}:{symbol}:{ts}",
                exchange=exchange,
                symbol=symbol,
                ts=ts,
                price=price,
                oi=oi,
            )
        return True
    except Exception:
        return False
    finally:
        d.close()


def write_prediction(prediction_id: str, exchange: str, symbol: str, ts: int, text: str, horizon_minutes: int) -> bool:
    """Create Prediction node and link to MarketState."""
    d = _driver()
    if not d:
        return False
    try:
        with d.session() as session:
            session.run(
                """
                CREATE (p:Prediction {id: $id})
                SET p.exchange = $exchange, p.symbol = $symbol, p.ts = $ts, p.text = $text, p.horizon_minutes = $horizon
                WITH p
                OPTIONAL MATCH (m:MarketState {exchange: $exchange, symbol: $symbol})
                WHERE m.ts <= $ts
                WITH p, m ORDER BY m.ts DESC LIMIT 1
                WHERE m IS NOT NULL
                MERGE (p)-[:ABOUT]->(m)
                """,
                id=prediction_id,
                exchange=exchange,
                symbol=symbol,
                ts=ts,
                text=text[:1000],
                horizon=horizon_minutes,
            )
        return True
    except Exception:
        return False
    finally:
        d.close()


def write_outcome(prediction_id: str, outcome: str, actual_price: float, reflection_text: str | None = None) -> bool:
    """Create Outcome node and link to Prediction. Optional reflection_text from DeepSeek R1."""
    d = _driver()
    if not d:
        return False
    try:
        with d.session() as session:
            session.run(
                """
                MATCH (p:Prediction {id: $pred_id})
                CREATE (o:Outcome {id: $oid})
                SET o.outcome = $outcome, o.actual_price = $actual_price, o.reflection = $reflection
                MERGE (o)-[:EVALUATES]->(p)
                """,
                pred_id=prediction_id,
                oid=f"{prediction_id}:outcome",
                outcome=outcome,
                actual_price=actual_price,
                reflection=reflection_text or "",
            )
        return True
    except Exception:
        return False
    finally:
        d.close()


def write_price_level(
    exchange: str, symbol: str, price: float, ts: int, vol_bid: float, vol_ask: float
) -> bool:
    """Create or update PriceLevel node (orderbook level snapshot)."""
    d = _driver()
    if not d:
        return False
    try:
        with d.session() as session:
            session.run(
                """
                MERGE (pl:PriceLevel {id: $id})
                SET pl.exchange = $exchange, pl.symbol = $symbol, pl.price = $price,
                    pl.ts = $ts, pl.vol_bid = $vol_bid, pl.vol_ask = $vol_ask
                """,
                id=f"{exchange}:{symbol}:{price}:{ts}",
                exchange=exchange,
                symbol=symbol,
                price=price,
                ts=ts,
                vol_bid=vol_bid,
                vol_ask=vol_ask,
            )
        return True
    except Exception:
        return False
    finally:
        d.close()


def write_trade(
    exchange: str, symbol: str, trade_id: str, ts: int, price: float, size: float, side: str
) -> bool:
    """Create Trade node."""
    d = _driver()
    if not d:
        return False
    try:
        with d.session() as session:
            session.run(
                """
                MERGE (t:Trade {id: $id})
                SET t.exchange = $exchange, t.symbol = $symbol, t.ts = $ts,
                    t.price = $price, t.size = $size, t.side = $side
                """,
                id=trade_id,
                exchange=exchange,
                symbol=symbol,
                ts=ts,
                price=price,
                size=size,
                side=side,
            )
        return True
    except Exception:
        return False
    finally:
        d.close()


def write_strategy_outcome(
    exchange: str,
    symbol: str,
    outcome_id: str,
    ts: int,
    direction: str,
    level: float,
    outcome_type: str = "entry",
) -> bool:
    """Create StrategyOutcome node (entry/exit at level). Link to MarketState via ABOUT."""
    d = _driver()
    if not d:
        return False
    try:
        with d.session() as session:
            session.run(
                """
                CREATE (s:StrategyOutcome {id: $id})
                SET s.exchange = $exchange, s.symbol = $symbol, s.ts = $ts,
                    s.direction = $direction, s.level = $level, s.outcome_type = $outcome_type
                WITH s
                OPTIONAL MATCH (m:MarketState {exchange: $exchange, symbol: $symbol})
                WHERE m.ts <= $ts
                WITH s, m ORDER BY m.ts DESC LIMIT 1
                WHERE m IS NOT NULL
                MERGE (s)-[:ABOUT]->(m)
                """,
                id=outcome_id,
                exchange=exchange,
                symbol=symbol,
                ts=ts,
                direction=direction,
                level=level,
                outcome_type=outcome_type,
            )
        return True
    except Exception:
        return False
    finally:
        d.close()


def write_rejected_at(event_id: str, exchange: str, symbol: str, price: float, ts: int) -> bool:
    """Link Event to PriceLevel as REJECTED_AT (e.g. breakout failed at level)."""
    d = _driver()
    if not d:
        return False
    try:
        with d.session() as session:
            session.run(
                """
                MATCH (e:Event {id: $event_id})
                WITH e
                OPTIONAL MATCH (pl:PriceLevel)
                WHERE pl.exchange = $exchange AND pl.symbol = $symbol AND pl.price = $price AND pl.ts <= $ts
                WITH e, pl ORDER BY pl.ts DESC LIMIT 1
                WHERE pl IS NOT NULL
                MERGE (e)-[:REJECTED_AT]->(pl)
                """,
                event_id=event_id,
                exchange=exchange,
                symbol=symbol,
                price=price,
                ts=ts,
            )
        return True
    except Exception:
        return False
    finally:
        d.close()
