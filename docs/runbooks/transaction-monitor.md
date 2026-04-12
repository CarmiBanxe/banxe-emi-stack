# Runbook: Transaction Monitor (AML)

**Service:** `services/transaction_monitor/`
**Router:** `/monitor` (main FastAPI app, port :8090)
**FCA rules:** MLR 2017 s.2.1, FATF Rec 10, FCA FG21/7
**Alert SLA:** < 2 seconds for scoring (I-27 HITL within 24h for CRITICAL)

---

## 1. Health Check

```bash
curl http://localhost:8090/monitor/health
# Expected: {"status": "ok"}
```

---

## 2. Score a Transaction (Test)

```bash
curl -X POST http://localhost:8090/monitor/score \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id": "tx-test-001",
    "customer_id": "cust-001",
    "amount": "9500.00",
    "currency": "GBP",
    "jurisdiction": "GB",
    "counterparty_jurisdiction": "GB",
    "is_crypto": false
  }'
```

---

## 3. Check Active Alerts

```bash
# All alerts
curl "http://localhost:8090/monitor/alerts"

# Filter CRITICAL only
curl "http://localhost:8090/monitor/alerts?severity=CRITICAL"

# Unreviewed HIGH alerts
curl "http://localhost:8090/monitor/alerts?severity=HIGH&status=PENDING"
```

---

## 4. Close a CRITICAL Alert (HITL Required)

```bash
curl -X PATCH http://localhost:8090/monitor/alerts/{alert_id} \
  -H "Content-Type: application/json" \
  -d '{
    "status": "CLOSED",
    "reviewer_notes": "Reviewed by CTIO 2026-04-12: legitimate payroll transaction, verified with customer"
  }'
# CRITICAL alerts REQUIRE reviewer_notes (I-27)
```

---

## 5. Velocity Check for Customer

```bash
curl http://localhost:8090/monitor/velocity/{customer_id}
# Returns: spend in last 1h / 24h / 7d
# EDD trigger: 24h cumulative ≥ £10,000 (I-04)
```

---

## 6. Dashboard Metrics

```bash
curl http://localhost:8090/monitor/metrics
# Returns: counts by severity/status, avg score, EDD count
```

---

## 7. Incident: False Positive Spike

1. Run `GET /monitor/metrics` — check if all HIGH/CRITICAL are from one customer/jurisdiction
2. Check velocity: `GET /monitor/velocity/{customer_id}`
3. If systematic: review RuleEngine thresholds via Jube UI (admin only)
4. Adjust only via Experiment Copilot (`POST /v1/experiments/design`) — never ad-hoc (I-27)
5. Document the change in the experiment audit trail

---

## 8. Escalation

- CRITICAL alert open > 24h without review: escalate to Compliance Officer
- Sanctioned jurisdiction transaction blocked: immediate MLRO notification
- EDD trigger (≥ £10k/24h): customer due diligence check required
