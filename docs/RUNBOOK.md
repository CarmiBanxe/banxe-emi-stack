# RUNBOOK — Banxe EMI Analytics Stack

**Audience:** On-call engineer (CEO / CTIO)
**Server:** GMKtec EVO-X2 · `ssh gmktec` · 192.168.0.72
**Last updated:** 2026-04-07 · IL-017

---

## Quick Reference

```bash
# Daily recon — manual trigger
ssh gmktec "cd /data/banxe-emi-stack && bash scripts/daily-recon.sh"

# Monthly FIN060 — manual trigger
ssh gmktec "cd /data/banxe-emi-stack && bash scripts/monthly-fin060.sh"

# Quality gate
ssh gmktec "cd /data/banxe-emi-stack && bash scripts/quality-gate.sh --fast"

# Logs
ssh gmktec "tail -100 /data/banxe/logs/daily-recon-$(date +%Y%m%d).log"
ssh gmktec "tail -100 /data/banxe/logs/fin060-cron.log"
```

---

## Incident Playbooks

### P1 · Daily Recon DISCREPANCY

**Symptom:** `daily-recon.sh` exits with code 1; Slack alert fired via n8n.

**FCA rule:** CASS 7.15.29R — alert within 1 business day; CASS 15.12 — breach report if persists ≥ 3 days.

**Steps:**
1. Check which account: `grep "DISCREPANCY" /data/banxe/logs/daily-recon-$(date +%Y%m%d).log`
2. Check ClickHouse for last 7 days:
   ```sql
   SELECT recon_date, account_type, internal_balance, external_balance, discrepancy
   FROM banxe.safeguarding_events
   WHERE status = 'DISCREPANCY'
   ORDER BY recon_date DESC
   LIMIT 10;
   ```
3. If bank statement missing (`source_file = ''`) → check SFTP / adorsys PSD2 gateway:
   ```bash
   curl http://localhost:8888/health
   ls /data/banxe/statements/
   ```
4. If Midaz balance wrong → check Midaz CBS:
   ```bash
   curl http://localhost:8095/v1/organizations/019d6301-32d7-70a1-bc77-0a05379ee510/ledgers/019d632f-519e-7865-8a30-3c33991bba9c/accounts/019d6332-f274-709a-b3a7-983bc8745886/balances
   ```
5. If discrepancy confirmed real → escalate to CEO + CTIO immediately. Do NOT wait.
6. If persists ≥ 3 business days → FCA RegData notification required (CASS 15.12).

---

### P1 · FIN060 Generation Failed

**Symptom:** `monthly-fin060.sh` exits non-zero; `/data/banxe/reports/fin060/` empty.

**Deadline:** 15th of the month following reporting period.

**Steps:**
1. Check log: `cat /data/banxe/logs/fin060-$(date +%Y%m).log`
2. Common causes:
   - `clickhouse-driver not installed` → `pip install clickhouse-driver`
   - `weasyprint not installed` → `pip install weasyprint`
   - ClickHouse unreachable → check `clickhouse-client -q "SELECT 1"`
   - No MATCHED rows for period → reconciliation not run; run daily-recon first
3. Manual retry: `bash scripts/monthly-fin060.sh 2026-03` (specify month)
4. Verify output: `ls -la /data/banxe/reports/fin060/`
5. Submit to FCA RegData manually if cron missed deadline window.

---

### P1 · ClickHouse Unreachable

**Symptom:** `ReconciliationEngine` fails with connection error; ClickHouse ping fails.

**Steps:**
1. Check service: `ssh gmktec "systemctl status clickhouse-server"`
2. Restart if down: `ssh gmktec "systemctl restart clickhouse-server"`
3. Verify: `ssh gmktec "clickhouse-client -q 'SELECT 1'"`
4. Check disk: `ssh gmktec "df -h /var/lib/clickhouse"`
5. Check schema intact:
   ```bash
   ssh gmktec "clickhouse-client -q 'SHOW TABLES FROM banxe'"
   ```
6. If data loss suspected — check backup: `ls /data/banxe/backups/clickhouse/`

**Note:** ClickHouse is append-only for audit tables (I-24). Never run DELETE/UPDATE on `safeguarding_events` or `payment_events`.

---

### P2 · Midaz CBS Unreachable

**Symptom:** `MidazLedgerAdapter.get_balance()` returns `Decimal("0")` for all accounts (fallback); log shows HTTP error.

**Steps:**
1. Check Midaz health: `curl http://localhost:8095/health`
2. Check if port is up: `ssh gmktec "ss -tlnp | grep 8095"`
3. Restart: `ssh gmktec "systemctl restart midaz"` (or docker: `docker restart midaz`)
4. If Midaz down at recon time → recon runs with PENDING status (expected, not a breach).
5. Rerun daily-recon manually once Midaz is back: `bash scripts/daily-recon.sh --date $(date +%Y-%m-%d)`

---

### P2 · n8n Webhook Alert Not Firing

**Symptom:** DISCREPANCY detected but no Slack alert.

**Steps:**
1. Check env: `grep N8N_WEBHOOK_URL /data/banxe/.env`
2. Test webhook manually:
   ```bash
   curl -X POST $N8N_WEBHOOK_URL -H "Content-Type: application/json" \
     -d '{"event":"TEST","message":"manual test"}'
   ```
3. Check n8n: `curl http://localhost:5678/healthz`
4. If n8n down → restart: `ssh gmktec "systemctl restart n8n"` (or `docker restart n8n`)
5. Note: missed alert does NOT mean missed breach detection — ClickHouse record is always written regardless.

---

### P3 · Payment Rail Failure (FPS / SEPA)

**Symptom:** `PaymentService.send()` returns `PaymentStatus.FAILED`.

**Steps:**
1. Check ClickHouse audit: `SELECT * FROM banxe.payment_events WHERE status = 'FAILED' ORDER BY event_time DESC LIMIT 10;`
2. If `PAYMENT_ADAPTER=mock` → MockAdapter running, no real money moved.
3. If `PAYMENT_ADAPTER=modulr` → check Modulr status page; verify `MODULR_API_KEY` in `.env`.
4. Check `MODULR_BASE_URL` in `.env` (sandbox vs production).
5. Idempotency: retry is safe — `idempotency_key` prevents double-payment.

---

## Scheduled Tasks (Cron — GMKtec)

| Schedule | Script | Purpose |
|----------|--------|---------|
| `0 7 * * 1-5` | `scripts/daily-recon.sh` | Daily safeguarding reconciliation (Mon-Fri) |
| `0 8 1 * *` | `scripts/monthly-fin060.sh` | Monthly FIN060 PDF (1st of month) |

Check cron: `ssh gmktec "crontab -l | grep banxe"`

---

## Emergency Contacts

| Role | Contact |
|------|---------|
| CEO | Moriel Carmi · @bereg2022 |
| CTIO | Олег · @p314pm |
| FCA RegData | https://regdata.fca.org.uk |

**FCA breach notification deadline:** 1 business day from detection (CASS 15.12).
