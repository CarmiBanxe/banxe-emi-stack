-- stg_ledger_transactions.sql
-- Staging: raw safeguarding events from ClickHouse → typed + cleaned
-- Source: banxe.safeguarding_events (append-only, I-24)
-- FCA CASS 7.15 | banxe-emi-stack

{{
    config(
        materialized='view'
    )
}}

SELECT
    toDate(recon_date)                              AS recon_date,
    account_id,
    account_type,
    currency,
    -- DECIMAL for all amounts — never float in downstream models
    toDecimal128(toString(internal_balance), 8)     AS internal_balance,
    toDecimal128(toString(external_balance), 8)     AS external_balance,
    toDecimal128(toString(discrepancy), 8)          AS discrepancy,
    status,
    alert_sent,
    source_file,
    created_at
FROM {{ source('banxe', 'safeguarding_events') }}
WHERE recon_date IS NOT NULL
