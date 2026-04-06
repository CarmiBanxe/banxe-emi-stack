-- fin060_monthly.sql
-- Mart: monthly aggregated FIN060a/b data for FCA RegData submission
-- FCA CASS 15 / PS25/12 | banxe-emi-stack

{{
    config(
        materialized='table',
        order_by='(report_month, account_type)'
    )
}}

SELECT
    toStartOfMonth(recon_date)                                   AS report_month,
    account_type,
    currency,

    -- FIN060a: average daily safeguarded amount (client_funds only)
    avgIf(external_balance, account_type = 'client_funds')       AS avg_daily_client_funds,
    maxIf(external_balance, account_type = 'client_funds')       AS peak_client_funds,

    -- Reconciliation quality metrics
    countIf(status = 'MATCHED')                                  AS days_matched,
    countIf(status = 'DISCREPANCY')                              AS days_discrepancy,
    countIf(status = 'PENDING')                                  AS days_pending,
    count()                                                      AS total_days,

    -- Largest discrepancy in period
    max(abs(discrepancy))                                        AS max_discrepancy

FROM {{ ref('safeguarding_daily') }}
GROUP BY
    report_month,
    account_type,
    currency
ORDER BY
    report_month DESC,
    account_type
