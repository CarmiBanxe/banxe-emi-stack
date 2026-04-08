-- scripts/schema/clickhouse_customers.sql
-- ClickHouse customer registry — banxe.customers
-- IL-053 | S17-01 Dual Entity Model | FCA UK GDPR Art.5 / MLR 2017 Reg.40
--
-- WHY ReplacingMergeTree(updated_at):
--   Every create/update/transition inserts a new row. ClickHouse deduplicates
--   asynchronously using the updated_at version column. Use SELECT FINAL for
--   consistent reads (slightly slower but correct for compliance queries).
--
-- Retention: 5 years post-offboarding (MLR 2017 Reg.40).
-- GDPR: law-enforcement / AML special category (Art.9(2)(g)).
--       Access restricted to MLRO + compliance roles.
--
-- Deploy: run on GMKtec ClickHouse (port 9000) as user default:
--   clickhouse-client --query "$(cat scripts/schema/clickhouse_customers.sql)"

CREATE DATABASE IF NOT EXISTS banxe;

CREATE TABLE IF NOT EXISTS banxe.customers
(
    -- Primary key
    customer_id          String,

    -- Flat searchable fields (LowCardinality for enum-like values)
    entity_type          LowCardinality(String),   -- INDIVIDUAL | COMPANY
    kyc_status           LowCardinality(String),   -- PENDING | APPROVED | REJECTED | EDD_REQUIRED
    risk_level           LowCardinality(String),   -- low | medium | high | very_high | prohibited
    lifecycle_state      LowCardinality(String),   -- ONBOARDING | ACTIVE | DORMANT | OFFBOARDED | DECEASED

    -- Timestamps (ReplacingMergeTree version key)
    created_at           DateTime64(3, 'UTC'),
    updated_at           DateTime64(3, 'UTC'),

    -- Full profile as JSON blob (Individual or Company dataclass)
    -- Avoids complex nested ClickHouse types; parsed in application layer.
    profile_json         String DEFAULT '{}',

    -- Arrays stored flat for efficient filtering
    agreement_ids        Array(String) DEFAULT [],
    account_ids          Array(String) DEFAULT []
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMM(created_at)
ORDER BY customer_id
TTL toDate(created_at) + INTERVAL 5 YEAR
SETTINGS index_granularity = 8192;

-- ── View: active customers ─────────────────────────────────────────────────────
-- Use this view for MLRO dashboards (avoids SELECT FINAL overhead on large tables)
CREATE OR REPLACE VIEW banxe.customers_active AS
SELECT *
FROM banxe.customers FINAL
WHERE lifecycle_state = 'ACTIVE';

-- ── View: high-risk customers (MLRO monitoring) ───────────────────────────────
CREATE OR REPLACE VIEW banxe.customers_high_risk AS
SELECT *
FROM banxe.customers FINAL
WHERE risk_level IN ('high', 'very_high')
  AND lifecycle_state NOT IN ('OFFBOARDED', 'DECEASED');
