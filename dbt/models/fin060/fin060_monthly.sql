-- dbt/models/fin060/fin060_monthly.sql — FIN060 Monthly Report dbt Model
-- IL-FIN060-01 | Phase 51C | Sprint 36
-- Incremental model, unique_key='period_key'
-- Amounts: numeric(20,8) — never float (I-01)

{{ config(
    materialized='incremental',
    unique_key='period_key',
    on_schema_change='fail'
) }}

WITH base AS (
    SELECT
        account_type,
        currency,
        DATE_TRUNC('month', transaction_date) AS period_month,
        TO_CHAR(DATE_TRUNC('month', transaction_date), 'YYYY-MM') AS period_key,
        SUM(amount::numeric(20,8)) AS balance  -- I-01: never float
    FROM {{ source('banxe_core', 'ledger_transactions') }}
    WHERE currency = 'GBP'
    {% if is_incremental() %}
        AND transaction_date >= (SELECT MAX(period_month) FROM {{ this }})
    {% endif %}
    GROUP BY account_type, currency, DATE_TRUNC('month', transaction_date)
),

safeguarding_totals AS (
    SELECT
        period_key,
        period_month,
        SUM(CASE WHEN account_type = 'safeguarding' THEN balance ELSE 0::numeric(20,8) END) AS total_safeguarded_gbp,
        SUM(CASE WHEN account_type = 'operational' THEN balance ELSE 0::numeric(20,8) END) AS total_operational_gbp,
        COUNT(*) AS entry_count
    FROM base
    GROUP BY period_key, period_month
)

SELECT
    period_key,
    period_month,
    total_safeguarded_gbp,
    total_operational_gbp,
    entry_count,
    'DRAFT' AS status,
    CURRENT_TIMESTAMP AS generated_at
FROM safeguarding_totals
