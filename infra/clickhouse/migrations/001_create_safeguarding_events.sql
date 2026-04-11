-- Migration 001: safeguarding_events table
-- FCA CASS 7.15 — daily reconciliation audit trail (5-year TTL, I-08)
CREATE DATABASE IF NOT EXISTS banxe;

CREATE TABLE IF NOT EXISTS banxe.safeguarding_events
(
    event_id         UUID            DEFAULT generateUUIDv4(),
    event_time       DateTime64(3)   DEFAULT now(),
    recon_date       Date,
    account_id       String,
    account_type     LowCardinality(String),
    currency         LowCardinality(String),
    internal_balance Decimal(18, 2),
    external_balance Decimal(18, 2),
    discrepancy      Decimal(18, 2),
    status           LowCardinality(String),
    alert_sent       UInt8           DEFAULT 0,
    source_file      String,
    created_by       String          DEFAULT 'recon-engine'
)
ENGINE = MergeTree()
ORDER BY (recon_date, account_id)
TTL recon_date + INTERVAL 5 YEAR
SETTINGS index_granularity = 8192;
