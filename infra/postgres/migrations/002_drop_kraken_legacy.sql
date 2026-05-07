-- Migration 002: Drop legacy kraken_order_id column.
-- Migration 001 already backfilled broker_order_id from kraken_order_id, so
-- this is safe. Idempotent — safe to re-run.

ALTER TABLE trades DROP COLUMN IF EXISTS kraken_order_id;
