-- Optional migration: pgvector for ai_experience similarity search.
-- Run after: CREATE EXTENSION IF NOT EXISTS vector;
-- Then: \i cold_schema_pgvector.sql

ALTER TABLE ai_experience ADD COLUMN IF NOT EXISTS embedding vector(1536);
CREATE INDEX IF NOT EXISTS idx_ai_experience_embedding ON ai_experience
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
