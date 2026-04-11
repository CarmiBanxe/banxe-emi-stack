-- Migration 002: safeguarding_breaches table
-- FCA CASS 15.12 — breach records (5-year TTL, I-08)
CREATE TABLE IF NOT EXISTS banxe.safeguarding_breaches
(
    detected_at      DateTime        DEFAULT now(),
    recon_date       Date,
    account_id       String,
    account_type     LowCardinality(String),
    currency         LowCardinality(String),
    discrepancy      Decimal(18, 2),
    days_outstanding UInt16          DEFAULT 1,
    reported_to_fca  UInt8           DEFAULT 0,
    notes            String          DEFAULT ''
)
ENGINE = MergeTree()
ORDER BY (detected_at, account_id)
TTL detected_at + INTERVAL 5 YEAR;
