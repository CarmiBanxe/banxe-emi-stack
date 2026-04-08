-- scripts/schema/clickhouse_webhooks.sql
-- ClickHouse webhook audit log — banxe.webhook_events
-- IL-053 | S17-03 | FCA I-24 (immutable audit trail, 5yr retention)
--
-- WHY THIS EXISTS:
--   Every inbound webhook from Modulr, Sumsub, n8n must be logged immutably
--   (FCA I-24). Append-only MergeTree — no UPDATE/DELETE ever.
--
-- Deploy: run on GMKtec ClickHouse (port 9000) as user default:
--   clickhouse-client --query "$(cat scripts/schema/clickhouse_webhooks.sql)"

CREATE DATABASE IF NOT EXISTS banxe;

CREATE TABLE IF NOT EXISTS banxe.webhook_events
(
    -- Unique webhook ID (uuid4 from WebhookRouter)
    webhook_id       String,

    -- Provider: modulr | sumsub | n8n | unknown
    provider         LowCardinality(String),

    -- Provider-specific event type: "payment.completed", "applicantReviewed", etc.
    event_type       String,

    -- Wall-clock time when webhook was received
    received_at      DateTime64(3, 'UTC') DEFAULT now64(3),

    -- Processing status: RECEIVED → VERIFIED → PROCESSED | FAILED
    status           LowCardinality(String),

    -- 1 if HMAC signature was valid
    signature_valid  UInt8 DEFAULT 0,

    -- Error message if status = FAILED | SIGNATURE_FAILED (empty string = no error)
    error            String DEFAULT ''
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(received_at)
ORDER BY (provider, received_at)
TTL toDate(received_at) + INTERVAL 5 YEAR
SETTINGS index_granularity = 8192;

-- ── View: signature failures (security monitoring) ────────────────────────────
CREATE OR REPLACE VIEW banxe.webhook_signature_failures AS
SELECT *
FROM banxe.webhook_events
WHERE signature_valid = 0
  AND status != 'RECEIVED'   -- exclude unprocessed (not yet verified)
ORDER BY received_at DESC;

-- ── View: failed webhooks (retry candidates) ─────────────────────────────────
CREATE OR REPLACE VIEW banxe.webhook_failures AS
SELECT *
FROM banxe.webhook_events
WHERE status = 'FAILED'
ORDER BY received_at DESC;
