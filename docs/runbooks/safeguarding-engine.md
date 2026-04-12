# Runbook: Safeguarding Engine (CASS 15)

**Service:** `services/safeguarding-engine/`
**Port:** :8091 (default)
**Schedule:** Daily recon via `scripts/daily-recon.sh` (07:00 UTC Mon-Fri)
**On-call:** CEO / CTIO
**FCA deadline:** Breach notification within 1 business day (CASS 15.12.4R)

---

## 1. Health Check

```bash
curl http://localhost:8091/health
# Expected: {"status": "ok", "service": "safeguarding-engine"}
```

---

## 2. Daily Reconciliation (Manual Trigger)

```bash
# Dry run first — no writes
curl -X POST http://localhost:8091/v1/reconciliation/run \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}'

# Live run (writes to DB + ClickHouse)
curl -X POST http://localhost:8091/v1/reconciliation/run \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```

Or via MCP: `mcp run reconciliation_status`

---

## 3. Check Current Position

```bash
curl http://localhost:8091/v1/safeguarding/position
# Returns: list of positions per account + currency
```

---

## 4. Check for Breaches

```bash
curl http://localhost:8091/v1/breaches
# Returns: list of active breach records
```

If breaches are present with `days_outstanding >= 3`: **FCA notification required within 1 business day**.

---

## 5. Restart Service

```bash
# Docker
docker-compose -f docker/docker-compose.recon.yml restart safeguarding-engine

# Verify
curl http://localhost:8091/health
```

---

## 6. Database Migration (Alembic)

```bash
cd services/safeguarding-engine
alembic upgrade head
```

Always run `alembic current` and check the migration list before applying. See `.claude/rules/60-migrations.md`.

---

## 7. Incident: DISCREPANCY Alert

1. Check which account: `GET /v1/reconciliation/status`
2. Check days outstanding: `GET /v1/breaches`
3. If ≥ 3 days: CEO must approve FCA notification (`POST /v1/breaches/report`)
4. Investigate root cause before any data correction
5. Never delete reconciliation records — create correction event

---

## 8. Escalation

- DISCREPANCY < 3 days: CTIO investigate
- DISCREPANCY ≥ 3 days: CEO + MLRO sign off on FCA notification
- ClickHouse audit query: `SELECT * FROM banxe.safeguarding_events WHERE event_date = today() ORDER BY timestamp DESC`
