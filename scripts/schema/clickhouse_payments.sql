-- ============================================================
-- ClickHouse Schema — Payment Events Audit Trail
-- Block C-fps + C-sepa, IL-014
-- FCA PSR / PSD2 / I-24 (append-only) / I-15 (TTL 5Y)
-- banxe-emi-stack
--
-- Run on GMKtec:
--   clickhouse-client --host localhost --port 9000 \
--     --query "$(cat scripts/schema/clickhouse_payments.sql)"
-- ============================================================

CREATE DATABASE IF NOT EXISTS banxe;

-- ── Payment Events: every submission + status update ─────────────────────────
-- Append-only (MergeTree — no DELETE/UPDATE).
-- One row per payment submission. Status updates via webhooks → new row.
-- FCA: must be producible on demand for PSR/FCA inspection.
CREATE TABLE IF NOT EXISTS banxe.payment_events
(
    -- Surrogate ID
    event_id             UUID            DEFAULT generateUUIDv4(),
    event_time           DateTime64(3)   DEFAULT now(),

    -- Payment identifiers
    idempotency_key      String          COMMENT 'Unique per payment attempt (UUID4)',
    provider_payment_id  String          COMMENT 'Modulr / ClearBank payment ID',

    -- Rail metadata
    rail                 LowCardinality(String)  COMMENT 'FPS | SEPA_CT | SEPA_INSTANT | BACS | CHAPS',
    direction            LowCardinality(String)  COMMENT 'OUTBOUND | INBOUND',

    -- Amount — Decimal for FCA I-24 compliance
    amount               Decimal(18, 2),
    currency             LowCardinality(String)  COMMENT 'GBP | EUR',

    -- Status
    status               LowCardinality(String)  COMMENT 'PENDING | PROCESSING | COMPLETED | FAILED | RETURNED | CANCELLED',
    error_code           String          DEFAULT '',
    error_message        String          DEFAULT '',

    -- Party names (not full PII — account numbers stored in Midaz, not here)
    debtor_name          String          DEFAULT '',
    creditor_name        String          DEFAULT '',
    reference            String          DEFAULT '',

    -- Timestamps
    submitted_at         String          COMMENT 'ISO-8601 UTC timestamp from adapter'
)
ENGINE = MergeTree()
ORDER BY (event_time, idempotency_key)
TTL event_time + INTERVAL 5 YEAR
SETTINGS index_granularity = 8192;

-- ── Payment Rails Summary MV: daily volume per rail ──────────────────────────
-- Materialized view for operations dashboard and FCA reporting.
CREATE MATERIALIZED VIEW IF NOT EXISTS banxe.mv_payment_daily_volume
ENGINE = SummingMergeTree()
ORDER BY (payment_date, rail, currency, status)
AS
SELECT
    toDate(event_time)          AS payment_date,
    rail,
    currency,
    status,
    count()                     AS payment_count,
    sum(amount)                 AS total_amount
FROM banxe.payment_events
GROUP BY payment_date, rail, currency, status;

-- ── Verification ──────────────────────────────────────────────────────────────
SELECT
    database,
    name AS table_name,
    engine
FROM system.tables
WHERE database = 'banxe'
  AND name IN ('payment_events', 'mv_payment_daily_volume')
ORDER BY name;
