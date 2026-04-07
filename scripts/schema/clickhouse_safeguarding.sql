-- ============================================================
-- ClickHouse Schema — Safeguarding Audit Trail
-- Block J-audit, IL-013 Sprint 9
-- FCA CASS 15 / PS25/12 | banxe-emi-stack
--
-- Run on GMKtec:
--   clickhouse-client --host localhost --port 9000 \
--     --query "$(cat scripts/schema/clickhouse_safeguarding.sql)"
--
-- Or via docker:
--   docker exec -i banxe-clickhouse clickhouse-client \
--     --query "$(cat scripts/schema/clickhouse_safeguarding.sql)"
--
-- FCA requirement: immutable append-only audit log, 5-year TTL (I-15, I-24)
-- ============================================================

-- Ensure database exists
CREATE DATABASE IF NOT EXISTS banxe;

-- ── Main reconciliation event table ──────────────────────────────────────────
-- One row per account per recon_date.
-- MergeTree is append-only by design.
-- TTL 5Y ensures FCA evidence retention (PS25/12 §7.4).
CREATE TABLE IF NOT EXISTS banxe.safeguarding_events
(
    inserted_at      DateTime        DEFAULT now()   COMMENT 'Wall-clock time of reconciliation run',
    recon_date       Date                            COMMENT 'Business date being reconciled',
    account_id       String                          COMMENT 'Midaz account UUID',
    account_type     LowCardinality(String)          COMMENT 'operational | client_funds',
    currency         LowCardinality(String)          COMMENT 'ISO-4217 e.g. GBP',
    internal_balance Float64                         COMMENT 'Midaz ledger balance (GBP major units)',
    external_balance Float64                         COMMENT 'Bank statement closing balance (CAMT.053/CSV)',
    discrepancy      Float64                         COMMENT 'external - internal',
    status           LowCardinality(String)          COMMENT 'MATCHED | DISCREPANCY | PENDING',
    alert_sent       UInt8           DEFAULT 0       COMMENT '1 if n8n webhook fired',
    source_file      String                          COMMENT 'Statement filename for traceability'
)
ENGINE = MergeTree()
ORDER BY (recon_date, account_id)
TTL recon_date + INTERVAL 5 YEAR
SETTINGS index_granularity = 8192;

-- ── FCA breach log ────────────────────────────────────────────────────────────
-- Separate table for FCA-reportable breaches (CASS 7.15.29R).
-- A breach = DISCREPANCY status persists for > 1 business day.
CREATE TABLE IF NOT EXISTS banxe.safeguarding_breaches
(
    detected_at      DateTime        DEFAULT now(),
    recon_date       Date,
    account_id       String,
    account_type     LowCardinality(String),
    currency         LowCardinality(String),
    discrepancy      Float64,
    days_outstanding UInt16          DEFAULT 1,
    reported_to_fca  UInt8           DEFAULT 0       COMMENT '1 if reported via FCA RegData',
    notes            String          DEFAULT ''
)
ENGINE = MergeTree()
ORDER BY (detected_at, account_id)
TTL detected_at + INTERVAL 5 YEAR;

-- ── Verification query (run after schema creation) ───────────────────────────
-- Expected output: two rows, one per table
SELECT
    database,
    name AS table_name,
    engine
FROM system.tables
WHERE database = 'banxe'
  AND name IN ('safeguarding_events', 'safeguarding_breaches')
ORDER BY name;
