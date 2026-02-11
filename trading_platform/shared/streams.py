"""
Redis Streams topic names and key patterns for the platform.
"""
STREAM_ORDERBOOK_UPDATES = "orderbook_updates"
STREAM_TRADES = "trades"
STREAM_KLINE = "kline"
STREAM_OPEN_INTEREST = "open_interest"
STREAM_LIQUIDATIONS = "liquidations"
STREAM_MAMBA_PREDICTIONS = "mamba_predictions"

REDIS_KEY_DOM = "dom:{exchange}:{symbol}"
REDIS_KEY_ORDERBOOK_SLICES = "orderbook_slices:{exchange}:{symbol}"
REDIS_KEY_TRADES = "trades:{exchange}:{symbol}"
REDIS_KEY_OI = "oi:{exchange}:{symbol}"
REDIS_KEY_LIQUIDATIONS = "liquidations:{exchange}:{symbol}"
REDIS_KEY_MAMBA_PREDICTIONS = "mamba_predictions:{exchange}:{symbol}"

OI_MAXLEN = 500
LIQUIDATIONS_MAXLEN = 500
SLICES_MAXLEN = 500
TRADES_MAXLEN = 2000
