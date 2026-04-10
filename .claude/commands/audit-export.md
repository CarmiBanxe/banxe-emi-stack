# /audit-export — Annual Audit Data Export
# Source: scripts/audit-export.sh
# Created: 2026-04-10
# Migration Phase: 3

## Description

Export safeguarding reconciliation events from ClickHouse for FCA/external auditor.
Produces a CSV of all `safeguarding_events` for the specified year.

## Prerequisites

- `clickhouse-client` CLI installed and accessible
- ClickHouse running with `banxe.safeguarding_events` table populated
- `.env` with `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`, `CLICKHOUSE_DB`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`

## Steps

1. **Export current year:**
   ```bash
   bash scripts/audit-export.sh
   ```

2. **Export specific year:**
   ```bash
   bash scripts/audit-export.sh 2025
   ```

3. **Custom output directory:**
   ```bash
   AUDIT_EXPORT_DIR=/tmp/audit bash scripts/audit-export.sh 2025
   ```

## Output

- CSV file: `${AUDIT_EXPORT_DIR:-/data/banxe/exports/audit}/safeguarding_events_YYYY.csv`
- Format: CSVWithNames (ClickHouse native), ordered by `recon_date, account_id`
- Contains: all columns from `banxe.safeguarding_events` for the given year

## Audit requirements

- FCA CASS 15: retain reconciliation records for 5 years minimum
- I-08: ClickHouse TTL enforces 5-year retention
- I-24: `safeguarding_events` is append-only (no UPDATE/DELETE)
- External auditors may request data annually or on-demand

## Post-export

1. Verify row count matches expected reconciliation days
2. Spot-check amounts against known reconciliation results
3. Provide CSV to external auditor alongside FIN060 PDF reports
4. Archive export with date stamp for internal records
