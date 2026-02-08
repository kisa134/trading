-- Add POC and Imbalance columns to footprint_bars (run once; on older PostgreSQL
-- ADD COLUMN may fail if column already exists — run manually if needed).
ALTER TABLE footprint_bars ADD COLUMN poc_price DOUBLE PRECISION;
ALTER TABLE footprint_bars ADD COLUMN imbalance_levels JSONB;
