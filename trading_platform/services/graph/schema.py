"""
Graph ontology: node labels and relationship types for market memory.
Nodes: MarketState, Event (liquidation, iceberg, wall, sweep), Prediction, Outcome.
Relationships: PRECEDES, NEXT, ABOUT, EVALUATES, LEADS_TO.
"""

NODE_MARKET_STATE = "MarketState"
NODE_EVENT = "Event"
NODE_PREDICTION = "Prediction"
NODE_OUTCOME = "Outcome"

REL_PRECEDES = "PRECEDES"
REL_NEXT = "NEXT"
REL_ABOUT = "ABOUT"
REL_EVALUATES = "EVALUATES"
REL_LEADS_TO = "LEADS_TO"
