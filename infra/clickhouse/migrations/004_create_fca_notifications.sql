-- Migration 004: fca_notifications table
-- FCA CASS 15.12 — RegData submission audit trail (5-year TTL, I-08)
CREATE TABLE IF NOT EXISTS banxe.fca_notifications
(
    notification_id   UUID            DEFAULT generateUUIDv4(),
    breach_account_id String,
    submitted_at      DateTime        DEFAULT now(),
    fca_reference     String          DEFAULT '',
    status            LowCardinality(String),   -- 'SUBMITTED' | 'FAILED' | 'PENDING'
    notes             String          DEFAULT ''
)
ENGINE = MergeTree()
ORDER BY (submitted_at, breach_account_id)
TTL submitted_at + INTERVAL 5 YEAR;
