-- scripts/schema/postgres_config.sql
-- PostgreSQL Config-as-Data schema — banxe product_config, fee_schedule, payment_limits
-- IL-053 | Geniusto v5 Pattern #6 | FCA COBS 6.1A / PSR 2017 Reg.67
--
-- WHY THIS EXISTS:
--   Fee schedules and payment limits must be hot-reloadable without a
--   deployment (FCA PS22/9 fair value obligation — fees can change).
--   PostgreSQL LISTEN/NOTIFY supports zero-downtime reload.
--
-- Deploy: run on GMKtec PostgreSQL (port 5432) as user banxe:
--   psql -h localhost -U banxe -d banxe_compliance -f scripts/schema/postgres_config.sql
--
-- Initial data: seeded from config/banxe_config.yaml — run scripts/seed_config.py

CREATE SCHEMA IF NOT EXISTS banxe;

-- ── Product catalogue ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS banxe.product_config
(
    product_id      TEXT        PRIMARY KEY,
    display_name    TEXT        NOT NULL,
    currencies      TEXT[]      NOT NULL DEFAULT '{GBP}',
    active          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE banxe.product_config IS
    'FCA COBS 6.1A: product catalogue — fee disclosure before account opening';

-- ── Fee schedules ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS banxe.fee_schedule
(
    id              SERIAL      PRIMARY KEY,
    product_id      TEXT        NOT NULL REFERENCES banxe.product_config(product_id) ON DELETE CASCADE,
    tx_type         TEXT        NOT NULL,   -- FPS | SEPA_CT | SEPA_INSTANT | BACS | FX | CARD_PAYMENT
    fee_type        TEXT        NOT NULL,   -- FLAT | PERCENTAGE | MIXED
    flat_fee        NUMERIC(18, 8) NOT NULL DEFAULT 0,
    percentage      NUMERIC(10, 8) NOT NULL DEFAULT 0,
    min_fee         NUMERIC(18, 8) NOT NULL DEFAULT 0,
    max_fee         NUMERIC(18, 8),         -- NULL = uncapped
    currency        TEXT        NOT NULL DEFAULT 'GBP',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (product_id, tx_type)
);

COMMENT ON TABLE banxe.fee_schedule IS
    'FCA COBS 6.1A / PSR 2017 Reg.67: fee per product + tx type';

-- ── Payment limits ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS banxe.payment_limits
(
    id                  SERIAL      PRIMARY KEY,
    product_id          TEXT        NOT NULL REFERENCES banxe.product_config(product_id) ON DELETE CASCADE,
    entity_type         TEXT        NOT NULL,   -- INDIVIDUAL | COMPANY
    single_tx_max       NUMERIC(18, 2) NOT NULL,
    daily_max           NUMERIC(18, 2) NOT NULL,
    monthly_max         NUMERIC(18, 2) NOT NULL,
    daily_tx_count      INTEGER     NOT NULL DEFAULT 9999,
    monthly_tx_count    INTEGER     NOT NULL DEFAULT 99999,
    min_tx              NUMERIC(18, 8) NOT NULL DEFAULT 0.01,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (product_id, entity_type)
);

COMMENT ON TABLE banxe.payment_limits IS
    'PSR 2017 Reg.67: payment limits per product + entity type';

-- ── Config version table (LISTEN/NOTIFY hot reload) ───────────────────────────

CREATE TABLE IF NOT EXISTS banxe.config_version
(
    id              SERIAL      PRIMARY KEY,
    version         INTEGER     NOT NULL DEFAULT 1,
    changed_by      TEXT        NOT NULL DEFAULT 'system',
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes           TEXT        DEFAULT ''
);

COMMENT ON TABLE banxe.config_version IS
    'Version counter for hot-reload via LISTEN/NOTIFY. Increment to trigger reload.';

-- Trigger: auto-NOTIFY on config change
CREATE OR REPLACE FUNCTION banxe.notify_config_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('config_changed', NEW.version::TEXT);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS config_change_notify ON banxe.config_version;
CREATE TRIGGER config_change_notify
    AFTER INSERT OR UPDATE ON banxe.config_version
    FOR EACH ROW EXECUTE FUNCTION banxe.notify_config_change();

-- ── Indexes ───────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_fee_schedule_product_id ON banxe.fee_schedule(product_id);
CREATE INDEX IF NOT EXISTS idx_payment_limits_product_id ON banxe.payment_limits(product_id);
CREATE INDEX IF NOT EXISTS idx_product_config_active ON banxe.product_config(active) WHERE active = TRUE;

-- ── Seed: EMI_ACCOUNT product (mirrors banxe_config.yaml) ────────────────────
-- This seed is idempotent (ON CONFLICT DO NOTHING).
-- For full seed from YAML: python3 scripts/seed_postgres_config.py

INSERT INTO banxe.product_config (product_id, display_name, currencies, active)
VALUES ('EMI_ACCOUNT', 'Banxe EMI Account', '{GBP,EUR,USD}', TRUE)
ON CONFLICT (product_id) DO NOTHING;

INSERT INTO banxe.fee_schedule (product_id, tx_type, fee_type, flat_fee, percentage, min_fee, max_fee, currency)
VALUES
    ('EMI_ACCOUNT', 'FPS',          'FLAT',       0.20, 0,      0.20, NULL,  'GBP'),
    ('EMI_ACCOUNT', 'BACS',         'FLAT',       0.10, 0,      0.10, NULL,  'GBP'),
    ('EMI_ACCOUNT', 'SEPA_CT',      'FLAT',       0.50, 0,      0.50, NULL,  'EUR'),
    ('EMI_ACCOUNT', 'SEPA_INSTANT', 'FLAT',       1.00, 0,      1.00, NULL,  'EUR'),
    ('EMI_ACCOUNT', 'FX',           'PERCENTAGE', 0,    0.0025, 1.00, 500.0, 'GBP'),
    ('EMI_ACCOUNT', 'CARD_PAYMENT', 'FLAT',       0,    0,      0,    NULL,  'GBP')
ON CONFLICT (product_id, tx_type) DO NOTHING;

INSERT INTO banxe.payment_limits
    (product_id, entity_type, single_tx_max, daily_max, monthly_max, daily_tx_count, monthly_tx_count, min_tx)
VALUES
    ('EMI_ACCOUNT', 'INDIVIDUAL', 25000,   50000,   150000,  50,  500,  0.01),
    ('EMI_ACCOUNT', 'COMPANY',    500000, 1000000, 5000000, 200, 2000, 0.01)
ON CONFLICT (product_id, entity_type) DO NOTHING;
