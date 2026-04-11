-- Migration 003: daily summary materialized view
CREATE MATERIALIZED VIEW IF NOT EXISTS banxe.recon_daily_summary
ENGINE = SummingMergeTree()
ORDER BY (recon_date, status)
AS SELECT
    recon_date,
    status,
    count() as count,
    sum(abs(discrepancy)) as total_discrepancy
FROM banxe.safeguarding_events
GROUP BY recon_date, status;
