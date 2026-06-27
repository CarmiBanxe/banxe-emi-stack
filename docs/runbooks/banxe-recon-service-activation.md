# Operator Runbook: banxe-recon Systemd Activation (GAP-087 Step 3)

**Status:** RED-ZONE — factory prepares, operator + HITL activates  
**FCA:** CASS 15 §7.15, CASS 7.15.29G, PS23/3 §3.49  
**HITL gate:** CTIO + CFO sign-off required before activation  

---

## Prerequisites

- [ ] GAP-087 Step 1 PR merged (ClickHouseStreakCounter wired)
- [ ] GAP-087 Step 2 PR merged (N8nFcaBreachNotifier wired)
- [ ] This PR merged (systemd unit + timer files)
- [ ] `N8N_FCA_WEBHOOK_URL` set in `/home/mmber/banxe-emi-stack/.env`
- [ ] Midaz CBS reachable from evo1 (`MIDAZ_BASE_URL`, `MIDAZ_API_KEY` in `.env`)
- [ ] ClickHouse reachable (`CLICKHOUSE_URL`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`)
- [ ] n8n FCA breach workflow active and tested

---

## Step 1 — Pre-activation dry run

Run on evo1 as mmber:

```bash
cd /home/mmber/banxe-emi-stack
python -m services.recon.cron_daily_recon --dry-run
```

Expected exit code: `0` (MATCHED) or `2` (PENDING — bank statement not yet received).  
If exit code `3` (FATAL): stop — fix infrastructure before activating.  
If exit code `1` (DISCREPANCY): stop — investigate before activating.

---

## Step 2 — Install systemd unit files

```bash
sudo cp deploy/systemd/banxe-recon.service /etc/systemd/system/
sudo cp deploy/systemd/banxe-recon.timer   /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/banxe-recon.service
sudo systemd-analyze verify /etc/systemd/system/banxe-recon.timer
```

---

## Step 3 — Enable and test

```bash
sudo systemctl daemon-reload
sudo systemctl enable banxe-recon.timer
sudo systemctl start banxe-recon.timer
# Verify timer active
sudo systemctl status banxe-recon.timer
# One-shot manual trigger to verify service
sudo systemctl start banxe-recon.service
sudo systemctl status banxe-recon.service
sudo journalctl -u banxe-recon.service -n 50
```

Expected: `Active: inactive (dead)` with `Result: exit-code` 0 (MATCHED) or 2 (PENDING).  
NOT expected: `failed` status.

---

## Common Failure Modes and Fixes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `EnvironmentFile not found` | `.env` missing | Create `/home/mmber/banxe-emi-stack/.env` with required vars |
| `python: No such file` | Wrong venv path | Verify `/opt/banxe/compliance/venv/bin/python` exists; update `ExecStart=` if different |
| `ModuleNotFoundError` | Wrong `WorkingDirectory` | Confirm `WorkingDirectory=/home/mmber/banxe-emi-stack` |
| `Permission denied` | Wrong `User=` | Confirm `mmber` owns the repo; update `User=/Group=` |
| Exit code `3` (FATAL) | Midaz/ClickHouse unreachable | Check `.env` URLs and network; test with `--dry-run` |

---

## HITL Gate

This activation is CASS 15 production critical. The following **humans** must sign off before enabling the timer:

| Role | Sign-off required |
|------|-----------------|
| CTIO | Confirms infra (Midaz, ClickHouse, n8n) are production-ready |
| CFO  | Confirms FCA notification path tested and MLRO notified |

Do NOT enable the timer without both sign-offs. Log sign-offs in the INSTRUCTION-LEDGER.md.

---

## Post-activation verification

The day after first run, confirm:

```bash
sudo journalctl -u banxe-recon.service --since yesterday
# Should show: STATUS=MATCHED or STATUS=PENDING, exit code 0 or 2
```

Check ClickHouse audit trail:

```sql
SELECT event_type, entity_id, occurred_at, severity
FROM banxe.safeguarding_audit
WHERE toDate(occurred_at) = today() - 1
AND actor = 'SafeguardingAgent'
ORDER BY occurred_at DESC
LIMIT 5;
```

---

## ADR references

- ADR-013: Midaz as primary CBS (no direct HTTP bypass)
- ADR-117/Hermes: RED-ZONE — factory prepares, operator activates
- GAP-087: S-PROD-1 Safeguarding Engine production delivery (ADR-140 Amendment 1)
