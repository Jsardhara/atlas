-- Migration 001: Alpaca broker migration.
-- Adds `broker_order_id` (broker-agnostic), keeps `kraken_order_id` for legacy reads.
-- Idempotent — safe to re-run.

ALTER TABLE trades ADD COLUMN IF NOT EXISTS broker_order_id TEXT;
ALTER TABLE trades DROP CONSTRAINT IF EXISTS trades_kraken_order_id_key;
ALTER TABLE trades ADD CONSTRAINT trades_broker_order_id_key UNIQUE (broker_order_id);

-- Backfill: copy kraken_order_id into broker_order_id where missing.
UPDATE trades SET broker_order_id = kraken_order_id
WHERE broker_order_id IS NULL AND kraken_order_id IS NOT NULL;
