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

-- AI predictions (cold history for Outcome Worker and Experience Replay)
CREATE TABLE IF NOT EXISTS ai_predictions (
    id UUID PRIMARY KEY,
    exchange VARCHAR(32) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    ts_prediction BIGINT NOT NULL,
    horizon_minutes INT NOT NULL,
    price_at_prediction DOUBLE PRECISION NOT NULL,
    target_price DOUBLE PRECISION,
    direction VARCHAR(16),
    expected_range_low DOUBLE PRECISION,
    expected_range_high DOUBLE PRECISION,
    snapshot_ref VARCHAR(256),
    context_snapshot JSONB,
    models_used JSONB,
    outcome VARCHAR(16),
    outcome_ts BIGINT,
    actual_price DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_pred_exchange_symbol_ts ON ai_predictions(exchange, symbol, ts_prediction);
CREATE INDEX IF NOT EXISTS idx_ai_pred_outcome ON ai_predictions(outcome) WHERE outcome IS NULL;

-- AI self-reflection (AgentRR: DeepSeek R1 analysis of failed predictions)
CREATE TABLE IF NOT EXISTS ai_reflections (
    id BIGSERIAL PRIMARY KEY,
    prediction_id UUID NOT NULL REFERENCES ai_predictions(id) ON DELETE CASCADE,
    reflection_text TEXT NOT NULL,
    model_used VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_reflections_prediction_id ON ai_reflections(prediction_id);

-- Experience Replay (few-shot): successful predictions + optional embedding for similarity search
CREATE TABLE IF NOT EXISTS ai_experience (
    id BIGSERIAL PRIMARY KEY,
    prediction_id UUID NOT NULL REFERENCES ai_predictions(id) ON DELETE CASCADE,
    exchange VARCHAR(32) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    outcome VARCHAR(16) NOT NULL DEFAULT 'success',
    summary_text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_experience_exchange_symbol ON ai_experience(exchange, symbol);
-- Optional: pgvector for similarity (run when extension available: CREATE EXTENSION IF NOT EXISTS vector;)
-- ALTER TABLE ai_experience ADD COLUMN IF NOT EXISTS embedding vector(1536);
-- CREATE INDEX IF NOT EXISTS idx_ai_experience_embedding ON ai_experience USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
