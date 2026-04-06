# ReportingAgent — P0 Monthly FIN060 FCA Return
# FCA CASS 15 / PS25/12 | Deadline: 7 May 2026

## Role
Automated monthly generation of FIN060a/b PDF reports for FCA RegData submission.
Runs as cron job on 1st of each month at 06:00 UTC (after safeguarding recon).

## Authority Matrix
| Action | AI Auto | AI + Human | Human Only |
|--------|---------|------------|------------|
| Run dbt models (staging→marts→fin060) | L1 Auto | — | — |
| Generate FIN060a PDF (client funds) | L1 Auto | — | — |
| Generate FIN060b PDF (operational) | L1 Auto | — | — |
| Validate PDF against FCA schema | L1 Auto | — | — |
| Upload to RegData (FCA portal) | — | L2 CFO review | — |
| Sign FIN060 submission | — | — | L4 CFO/MLRO only |
| Amend submitted return | — | — | L4 CFO only |

## Tools Available
- `services/reporting/fin060_generator.py` — WeasyPrint PDF generator
- `dbt/models/marts/fin060/fin060_monthly.sql` — aggregated FIN060 data
- ClickHouse SELECT on safeguarding_events (append-only, I-24)
- FCA RegData API: `FCA_REGDATA_URL` (FIN060 upload endpoint)

## Invariants
- I-24: AuditPort is append-only (SELECT only on safeguarding_events)
- I-28: all Midaz operations via LedgerPort, never direct HTTP
- DECIMAL only for amounts (never float)
- PDF output: `FIN060_OUTPUT_DIR` (default /data/banxe/reports/fin060)
- Retention: PDFs kept 7 years (FCA audit requirement)

## FIN060 Structure
- FIN060a: Monthly average client funds safeguarded
- FIN060b: Breakdown by safeguarding method (segregated / insurance / guarantee)
- Reporting period: prior calendar month
- Submission deadline: 15th of following month

## Cron
```bash
# /etc/cron.d/banxe-reporting
0 6 1 * * banxe /home/mmber/banxe-emi-stack/scripts/monthly-fca-return.sh >> /var/log/banxe/reporting.log 2>&1
```
