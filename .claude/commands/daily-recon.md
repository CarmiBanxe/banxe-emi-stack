# /daily-recon — Trigger Daily Safeguarding Reconciliation
# Source: scripts/daily-recon.sh, services/recon/cron_daily_recon.py
# Created: 2026-04-10
# Migration Phase: 3

## Description

Run FCA CASS 7.15 daily safeguarding reconciliation.
Compares Midaz ledger balances against bank statements (CAMT.053).
Production: runs via systemd timer at 07:00 UTC Mon–Fri on GMKtec.

## Prerequisites

- `.env` loaded with `MIDAZ_BASE_URL`, `CLICKHOUSE_HOST`, `STATEMENT_DIR`
- ClickHouse running with `banxe.safeguarding_events` table
- For PSD2 polling: `SAFEGUARDING_OPERATIONAL_IBAN` + `SAFEGUARDING_CLIENT_FUNDS_IBAN` set

## Steps

1. **Dry run (no ClickHouse writes):**
   ```bash
   DRY_RUN=1 bash scripts/daily-recon.sh
   ```

2. **Full run (today):**
   ```bash
   bash scripts/daily-recon.sh
   ```

3. **Specific date:**
   ```bash
   bash scripts/daily-recon.sh 2026-04-09
   ```

4. **Via Python module (systemd path):**
   ```bash
   python3 -m services.recon.cron_daily_recon --dry-run
   ```

## Exit codes

| Code | Meaning | FCA action |
|------|---------|------------|
| 0 | ALL MATCHED | None |
| 1 | DISCREPANCY | Investigate within 1 business day (CASS 7.15.29R) |
| 2 | PENDING (no statement) | Retry when statement available |
| 3 | FATAL | Infrastructure failure — fix immediately |

## Production deployment

- Systemd timer: `banxe-recon.timer` on GMKtec (07:00 UTC Mon–Fri)
- Check status: `ssh gmktec 'systemctl status banxe-recon.timer'`
- Logs: `/var/log/banxe/recon-YYYY-MM-DD.log`
- n8n webhook fires on discrepancy → Telegram MLRO alert

## FCA references

- CASS 7.15.17R: daily reconciliation requirement
- CASS 7.15.29R: investigate discrepancies within 1 business day
- I-15: retain logs 5 years
