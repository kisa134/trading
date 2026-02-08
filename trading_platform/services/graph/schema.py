"""
Graph ontology: node labels and relationship types for market memory.
Nodes: MarketState, Event (liquidation, iceberg, wall, sweep), Prediction, Outcome, PriceMove,
       PriceLevel, Trade, StrategyOutcome.
Relationships: PRECEDES, NEXT, ABOUT, EVALUATES, LEADS_TO, FOLLOWED_BY, REJECTED_AT.
"""

NODE_MARKET_STATE = "MarketState"
NODE_EVENT = "Event"
NODE_PREDICTION = "Prediction"
NODE_OUTCOME = "Outcome"
NODE_PRICE_MOVE = "PriceMove"
NODE_PRICE_LEVEL = "PriceLevel"
NODE_TRADE = "Trade"
NODE_STRATEGY_OUTCOME = "StrategyOutcome"

REL_PRECEDES = "PRECEDES"
REL_NEXT = "NEXT"
REL_ABOUT = "ABOUT"
REL_EVALUATES = "EVALUATES"
REL_LEADS_TO = "LEADS_TO"
REL_FOLLOWED_BY = "FOLLOWED_BY"
REL_REJECTED_AT = "REJECTED_AT"
