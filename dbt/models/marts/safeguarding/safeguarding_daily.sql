-- safeguarding_daily.sql
-- Mart: one row per account per day with recon status
-- Used by: FIN060 generator, MLRO dashboard, FCA audit export
-- FCA CASS 7.15 | banxe-emi-stack

{{
    config(
        materialized='table',
        order_by='(recon_date, account_id)'
    )
}}

SELECT
    recon_date,
    account_id,
    account_type,
    currency,
    internal_balance,
    external_balance,
    discrepancy,
    status,
    alert_sent,
    source_file,
    -- Derived flags for FCA reporting
    abs(discrepancy) > toDecimal128('1.00', 8)  AS is_discrepancy,
    status = 'PENDING'                           AS is_pending,
    status = 'MATCHED'                           AS is_matched
FROM {{ ref('stg_ledger_transactions') }}
ORDER BY recon_date DESC, account_id
