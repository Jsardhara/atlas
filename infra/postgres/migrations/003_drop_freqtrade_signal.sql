-- Migration 003: Drop legacy freqtrade_signal column on signals table.
-- Freqtrade was removed from the stack in chore/drop-freqtrade.
-- Idempotent — safe to re-run.

ALTER TABLE signals DROP COLUMN IF EXISTS freqtrade_signal;
