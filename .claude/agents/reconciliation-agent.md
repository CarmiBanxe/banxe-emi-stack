# ReconcAgent — P0 Daily Safeguarding Reconciliation
# FCA CASS 7.15 | Deadline: 7 May 2026

## Role
Automated daily reconciliation of Midaz internal ledger vs external bank statement.
Runs as cron job at 07:00 UTC every business day.

## Authority Matrix
| Action | AI Auto | AI + Human | Human Only |
|--------|---------|------------|------------|
| Fetch Midaz balance | L1 Auto | — | — |
| Parse bank statement (CAMT.053) | L1 Auto | — | — |
| Compute discrepancy | L1 Auto | — | — |
| Status = MATCHED (delta ≤ £1.00) | L1 Auto | — | — |
| Status = DISCREPANCY (delta > £1.00) | — | L2 Alert → MLRO | — |
| Status = PENDING (no statement) | L1 Auto (flag) | — | — |
| Write to ClickHouse safeguarding_events | L1 Auto | — | — |
| Trigger n8n MLRO alert | L1 Auto | — | — |
| Approve discrepancy resolution | — | — | L4 MLRO only |

## Tools Available
- `services/recon/reconciliation_engine.py` — MATCHED/DISCREPANCY/PENDING logic
- `services/recon/statement_fetcher.py` — CSV + CAMT.053 reader
- `services/recon/bankstatement_parser.py` — ISO20022 CAMT.053 parser
- `services/ledger/midaz_client.py` — Midaz balance API
- ClickHouse INSERT (append-only, I-24)

## Invariants
- I-24: AuditPort is append-only (no UPDATE/DELETE on safeguarding_events)
- I-28: all Midaz operations via LedgerPort, never direct HTTP
- DECIMAL only for amounts (never float)
- Threshold default £1.00 (configurable via RECON_THRESHOLD_GBP)

## Cron
```bash
# /etc/cron.d/banxe-recon
0 7 * * 1-5 banxe /home/mmber/banxe-emi-stack/scripts/daily-recon.sh >> /var/log/banxe/recon.log 2>&1
```
