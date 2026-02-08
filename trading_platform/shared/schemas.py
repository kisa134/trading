"""
Normalized message schemas for the platform (all exchanges -> same format).
"""
# orderbook_event: exchange, symbol, type (snapshot|delta), ts, bids [[price, size]], asks [[price, size]], update_id?
# trade: exchange, symbol, side, price, size, ts, trade_id
# candle: exchange, symbol, interval, start, open, high, low, close, volume, confirm

EXCHANGE_FIELD = "exchange"
SYMBOL_FIELD = "symbol"
TYPE_FIELD = "type"
TS_FIELD = "ts"
BIDS_FIELD = "bids"
ASKS_FIELD = "asks"
UPDATE_ID_FIELD = "update_id"
SIDE_FIELD = "side"
PRICE_FIELD = "price"
SIZE_FIELD = "size"
TRADE_ID_FIELD = "trade_id"
INTERVAL_FIELD = "interval"
START_FIELD = "start"
OPEN_FIELD = "open"
HIGH_FIELD = "high"
LOW_FIELD = "low"
CLOSE_FIELD = "close"
VOLUME_FIELD = "volume"
CONFIRM_FIELD = "confirm"
SCORE_CANDLE_FIELD = "score_candle"
SCORE_VOLUME_FIELD = "score_volume"
SCORE_ORDERBOOK_FIELD = "score_orderbook"
SCORE_IMPULSE_FIELD = "score_impulse"
TREND_POWER_FIELD = "trend_power"
TREND_POWER_DELTA_FIELD = "trend_power_delta"
EXHAUSTION_SCORE_FIELD = "exhaustion_score"
ABSORPTION_SCORE_FIELD = "absorption_score"
PROB_REVERSAL_FIELD = "prob_reversal_rule"
REVERSAL_HORIZON_FIELD = "reversal_horizon_bars"
EXPECTED_RANGE_FIELD = "expected_move_range"
OPEN_INTEREST_FIELD = "open_interest"
OPEN_INTEREST_VALUE_FIELD = "open_interest_value"
QUANTITY_FIELD = "quantity"


def orderbook_event(exchange: str, symbol: str, event_type: str, ts: int, bids: list, asks: list, update_id=None) -> dict:
    return {
        EXCHANGE_FIELD: exchange,
        SYMBOL_FIELD: symbol,
        TYPE_FIELD: event_type,
        TS_FIELD: ts,
        BIDS_FIELD: bids,
        ASKS_FIELD: asks,
        **({} if update_id is None else {UPDATE_ID_FIELD: update_id}),
    }


def trade_event(exchange: str, symbol: str, side: str, price: float, size: float, ts: int, trade_id=None) -> dict:
    return {
        EXCHANGE_FIELD: exchange,
        SYMBOL_FIELD: symbol,
        SIDE_FIELD: side,
        PRICE_FIELD: price,
        SIZE_FIELD: size,
        TS_FIELD: ts,
        **({} if trade_id is None else {TRADE_ID_FIELD: trade_id}),
    }


def candle_event(exchange: str, symbol: str, interval: str, start: int, o: float, h: float, lo: float, c: float, vol: float, confirm: bool) -> dict:
    return {
        EXCHANGE_FIELD: exchange,
        SYMBOL_FIELD: symbol,
        INTERVAL_FIELD: interval,
        START_FIELD: start,
        OPEN_FIELD: o,
        HIGH_FIELD: h,
        LOW_FIELD: lo,
        CLOSE_FIELD: c,
        VOLUME_FIELD: vol,
        CONFIRM_FIELD: confirm,
    }


def trend_score_event(
    exchange: str,
    symbol: str,
    ts: int,
    score_candle: float,
    score_volume: float,
    score_orderbook: float,
    score_impulse: float,
    trend_power: float,
    trend_power_delta: float,
) -> dict:
    return {
        EXCHANGE_FIELD: exchange,
        SYMBOL_FIELD: symbol,
        TS_FIELD: ts,
        SCORE_CANDLE_FIELD: score_candle,
        SCORE_VOLUME_FIELD: score_volume,
        SCORE_ORDERBOOK_FIELD: score_orderbook,
        SCORE_IMPULSE_FIELD: score_impulse,
        TREND_POWER_FIELD: trend_power,
        TREND_POWER_DELTA_FIELD: trend_power_delta,
    }


def exhaustion_event(exchange: str, symbol: str, ts: int, exhaustion_score: float, absorption_score: float) -> dict:
    return {
        EXCHANGE_FIELD: exchange,
        SYMBOL_FIELD: symbol,
        TS_FIELD: ts,
        EXHAUSTION_SCORE_FIELD: exhaustion_score,
        ABSORPTION_SCORE_FIELD: absorption_score,
    }


def rule_reversal_event(
    exchange: str,
    symbol: str,
    ts: int,
    prob_reversal_rule: float,
    reversal_horizon_bars: int,
    expected_move_range: list,
) -> dict:
    return {
        EXCHANGE_FIELD: exchange,
        SYMBOL_FIELD: symbol,
        TS_FIELD: ts,
        PROB_REVERSAL_FIELD: prob_reversal_rule,
        REVERSAL_HORIZON_FIELD: reversal_horizon_bars,
        EXPECTED_RANGE_FIELD: expected_move_range,
    }


def open_interest_event(
    exchange: str,
    symbol: str,
    ts: int,
    open_interest: float,
    open_interest_value: float | None = None,
) -> dict:
    return {
        EXCHANGE_FIELD: exchange,
        SYMBOL_FIELD: symbol,
        TS_FIELD: ts,
        OPEN_INTEREST_FIELD: open_interest,
        **({} if open_interest_value is None else {OPEN_INTEREST_VALUE_FIELD: open_interest_value}),
    }


def liquidation_event(
    exchange: str,
    symbol: str,
    ts: int,
    price: float,
    quantity: float,
    side: str,
) -> dict:
    """Side: Buy = liquidation of Long, Sell = liquidation of Short."""
    return {
        EXCHANGE_FIELD: exchange,
        SYMBOL_FIELD: symbol,
        TS_FIELD: ts,
        PRICE_FIELD: price,
        QUANTITY_FIELD: quantity,
        SIDE_FIELD: side,
    }
