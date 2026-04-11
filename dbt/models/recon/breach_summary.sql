-- Safeguarding breach summary
-- Sources: banxe.safeguarding_breaches (ClickHouse)
-- FCA CASS 15.12: breach audit trail for FCA inspection
-- Retention: 90-day rolling window (full history in ClickHouse with 5yr TTL)
{{ config(materialized='table') }}

SELECT
    detected_at,
    recon_date,
    account_id,
    account_type,
    currency,
    discrepancy,
    days_outstanding,
    reported_to_fca,
    notes,
    -- Calculated fields for reporting
    CASE
        WHEN reported_to_fca = 1 THEN 'FCA_NOTIFIED'
        WHEN days_outstanding >= 3 THEN 'BREACH_ACTIVE'
        ELSE 'MONITORING'
    END AS breach_status,
    CASE
        WHEN days_outstanding >= 7 THEN 'CRITICAL'
        WHEN days_outstanding >= 3 THEN 'HIGH'
        ELSE 'MEDIUM'
    END AS severity
FROM {{ source('clickhouse', 'safeguarding_breaches') }}
WHERE detected_at >= dateadd(day, -90, current_date)
ORDER BY detected_at DESC, days_outstanding DESC
