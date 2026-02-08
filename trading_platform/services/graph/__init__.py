"""
Graph memory: Neo4j (or FalkorDB). Events -> nodes; GraphRAG for AI context.
Optional: set NEO4J_URI to enable.
"""

from .schema import NODE_MARKET_STATE, NODE_EVENT, NODE_PREDICTION, NODE_OUTCOME
from .writer import write_event, write_market_state, write_prediction, write_outcome
from .graphrag import query_similar_situations

__all__ = [
    "NODE_MARKET_STATE",
    "NODE_EVENT",
    "NODE_PREDICTION",
    "NODE_OUTCOME",
    "write_event",
    "write_market_state",
    "write_prediction",
    "write_outcome",
    "query_similar_situations",
]
