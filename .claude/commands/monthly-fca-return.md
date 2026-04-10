# /monthly-fca-return — Generate FIN060 and Submit to RegData
# Source: scripts/monthly-fca-return.sh, scripts/monthly-fin060.sh, services/reporting/fin060_generator.py
# Created: 2026-04-10
# Migration Phase: 3

## Description

Generate monthly FCA FIN060a/b safeguarding return PDF.
Two scripts exist: `monthly-fca-return.sh` (dbt + PDF) and `monthly-fin060.sh` (PDF only).
Submission deadline: 15th of the following month via FCA RegData portal.

## Prerequisites

- ClickHouse with reconciliation data for the reporting period
- `clickhouse-driver` and `weasyprint` Python packages installed
- `dbt-clickhouse` for the dbt model path
- `.env` with ClickHouse credentials

## Steps

1. **Generate PDF (previous month, default):**
   ```bash
   bash scripts/monthly-fin060.sh
   ```

2. **Generate PDF (specific month):**
   ```bash
   bash scripts/monthly-fin060.sh 2026-03
   ```

3. **Full pipeline (dbt model + PDF):**
   ```bash
   bash scripts/monthly-fca-return.sh
   ```

4. **Full pipeline (specific period):**
   ```bash
   bash scripts/monthly-fca-return.sh 2026 03
   ```

## Output

- PDF saved to `${FIN060_OUTPUT_DIR:-/data/banxe/reports/fin060}/`
- Filename: `FIN060_YYYY-MM.pdf`

## Post-generation (manual)

1. CFO/MLRO review and sign-off on PDF
2. Upload to FCA RegData portal
3. Archive signed copy in audit trail

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | PDF generated successfully |
| 1 | Generation failed |
| 2 | clickhouse-driver not installed |
| 3 | weasyprint not installed |

## Cron schedule (production)

```
0 8 1 * * /data/banxe/banxe-emi-stack/scripts/monthly-fin060.sh >> /var/log/banxe/fin060.log 2>&1
```

## FCA references

- FCA CASS 15: safeguarding returns
- PS25/12: updated reporting requirements
- Deadline: 15th of the month following the reporting period
