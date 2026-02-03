-- Cold storage schema (PostgreSQL / TimescaleDB)
-- Run once to create tables.

CREATE TABLE IF NOT EXISTS trades (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(32) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    side VARCHAR(8) NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    size DOUBLE PRECISION NOT NULL,
    ts BIGINT NOT NULL,
    trade_id VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_trades_exchange_symbol_ts ON trades(exchange, symbol, ts);

CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(32) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    ts BIGINT NOT NULL,
    bids JSONB NOT NULL,
    asks JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ob_exchange_symbol_ts ON orderbook_snapshots(exchange, symbol, ts);

CREATE TABLE IF NOT EXISTS heatmap_rows (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(32) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    ts BIGINT NOT NULL,
    price_bin DOUBLE PRECISION NOT NULL,
    volume_bid DOUBLE PRECISION NOT NULL,
    volume_ask DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_heatmap_exchange_symbol_ts ON heatmap_rows(exchange, symbol, ts);

CREATE TABLE IF NOT EXISTS footprint_bars (
    id BIGSERIAL PRIMARY KEY,
    exchange VARCHAR(32) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    bar_start BIGINT NOT NULL,
    bar_end BIGINT NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    volume_bid DOUBLE PRECISION NOT NULL,
    volume_ask DOUBLE PRECISION NOT NULL,
    delta DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_footprint_exchange_symbol_start ON footprint_bars(exchange, symbol, bar_start);

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    type VARCHAR(64) NOT NULL,
    exchange VARCHAR(32) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    price DOUBLE PRECISION,
    side VARCHAR(8),
    volume DOUBLE PRECISION,
    ts_start BIGINT,
    ts_end BIGINT,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_events_exchange_symbol_ts ON events(exchange, symbol, ts_start);
