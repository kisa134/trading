"""
Redis Streams topic names and key patterns for the platform.
"""
STREAM_ORDERBOOK_UPDATES = "orderbook_updates"
STREAM_TRADES = "trades"
STREAM_KLINE = "kline"
STREAM_HEATMAP_SLICES = "heatmap_slices"
STREAM_FOOTPRINT_BARS = "footprint_bars"
STREAM_EVENTS = "events"
STREAM_SCORES_TREND = "scores.trend"
STREAM_SCORES_EXHAUSTION = "scores.exhaustion"
STREAM_SIGNALS_RULE_REVERSAL = "signals.rule_reversal"

REDIS_KEY_DOM = "dom:{exchange}:{symbol}"
REDIS_KEY_ORDERBOOK_SLICES = "orderbook_slices:{exchange}:{symbol}"
REDIS_KEY_TRADES = "trades:{exchange}:{symbol}"
REDIS_KEY_EVENTS = "events:{exchange}:{symbol}"
REDIS_KEY_HEATMAP = "heatmap:{exchange}:{symbol}"
REDIS_KEY_FOOTPRINT = "footprint:{exchange}:{symbol}"
REDIS_KEY_TAPE = "tape:{exchange}:{symbol}"
REDIS_KEY_SCORES_TREND = "scores.trend:{exchange}:{symbol}"
REDIS_KEY_SCORES_EXHAUSTION = "scores.exhaustion:{exchange}:{symbol}"
REDIS_KEY_SIGNALS_RULE = "signals.rule_reversal:{exchange}:{symbol}"
REDIS_KEY_SCORE_CANDLE = "scores.candle:{exchange}:{symbol}"
REDIS_KEY_SCORE_VOLUME = "scores.volume:{exchange}:{symbol}"
REDIS_KEY_SCORE_ORDERBOOK = "scores.orderbook:{exchange}:{symbol}"

SLICES_MAXLEN = 500
TRADES_MAXLEN = 2000
EVENTS_MAXLEN = 200
SCORES_MAXLEN = 500
SIGNALS_MAXLEN = 200
