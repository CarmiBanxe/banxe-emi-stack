-- Safeguarding daily reconciliation status
-- Sources: banxe.safeguarding_events (ClickHouse)
-- FCA CASS 7.15: daily audit trail for safeguarding reconciliation
-- Retention: 90-day rolling window (full history in ClickHouse with 5yr TTL)
{{ config(materialized='table') }}

SELECT
    recon_date,
    account_id,
    account_type,
    currency,
    internal_balance,
    external_balance,
    discrepancy,
    status,
    source_file
FROM {{ source('clickhouse', 'safeguarding_events') }}
WHERE recon_date >= dateadd(day, -90, current_date)
ORDER BY recon_date DESC, account_id
