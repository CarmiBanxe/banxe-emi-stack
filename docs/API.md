# API Reference — Banxe EMI Analytics Stack

**Version:** 1.0.0 | **Updated:** 2026-04-12 | IL-RETRO-02 (backfill: IL-046..IL-072)

Public interfaces for all domain services. Internal helpers are not documented here.

---

## ReconciliationEngine

**Module:** `services.recon.reconciliation_engine`
**FCA rule:** CASS 7.15 daily reconciliation

### Constructor

```python
ReconciliationEngine(
    ledger_port: LedgerPortProtocol,
    ch_client: ClickHouseClientProtocol,
    statement_fetcher: StatementFetcherProtocol,
    threshold: Decimal = Decimal("1.00"),   # CEO Q3: £1.00 discrepancy tolerance
    org_id: str = ORG_ID,
    ledger_id: str = LEDGER_ID,
)
```

### `reconcile(recon_date: date) → List[ReconResult]`

Run daily reconciliation for all safeguarding accounts.

```python
from datetime import date
from services.recon.reconciliation_engine import ReconciliationEngine
from services.recon.clickhouse_client import InMemoryReconClient
from services.ledger.midaz_adapter import StubLedgerAdapter
from services.recon.statement_fetcher import StatementFetcher

engine = ReconciliationEngine(
    ledger_port=StubLedgerAdapter({"acct-id": Decimal("100000.00")}),
    ch_client=InMemoryReconClient(),
    statement_fetcher=StatementFetcher(),
)
results = engine.reconcile(date.today())
# [ReconResult(status="MATCHED"|"DISCREPANCY"|"PENDING", ...)]
```

### `ReconResult` fields

| Field | Type | Description |
|-------|------|-------------|
| `recon_date` | `date` | Date reconciled |
| `account_id` | `str` | Midaz account UUID |
| `account_type` | `str` | `"operational"` or `"client_funds"` |
| `currency` | `str` | ISO-4217 (default `"GBP"`) |
| `internal_balance` | `Decimal` | Balance from Midaz CBS |
| `external_balance` | `Decimal` | Balance from bank statement |
| `discrepancy` | `Decimal` | `external - internal` (positive = bank has more) |
| `status` | `str` | `"MATCHED"` / `"DISCREPANCY"` / `"PENDING"` |
| `source_file` | `str` | Statement filename (empty if PENDING) |
| `alert_sent` | `bool` | True if n8n alert was fired |

---

## BreachDetector

**Module:** `services.recon.breach_detector`
**FCA rule:** CASS 15.12 — notify FCA within 1 business day if breach persists ≥ 3 days

### Constructor

```python
BreachDetector(
    ch_client: BreachClientProtocol,
    breach_days: int = 3,                      # configurable via BREACH_DAYS env
    amount_threshold: Decimal = Decimal("10.00"),  # configurable via BREACH_AMOUNT_GBP env
)
```

### `check_and_escalate(results: list, recon_date: date) → List[BreachRecord]`

Call after `ReconciliationEngine.reconcile()`. Checks for persisting DISCREPANCYs.

```python
detector = BreachDetector(ch_client)
breaches = detector.check_and_escalate(results, date.today())
# Returns [] if no breach, or list of BreachRecord written to safeguarding_breaches
```

### `BreachRecord` fields

| Field | Type | Description |
|-------|------|-------------|
| `account_id` | `str` | Midaz account UUID |
| `account_type` | `str` | `"operational"` or `"client_funds"` |
| `currency` | `str` | ISO-4217 |
| `discrepancy` | `Decimal` | Absolute discrepancy amount |
| `days_outstanding` | `int` | Consecutive DISCREPANCY days |
| `first_seen` | `date` | Date streak started |
| `latest_date` | `date` | Most recent DISCREPANCY date |

---

## FCARegDataClient

**Module:** `services.recon.fca_regdata_client`
**FCA rule:** CASS 15.12 — breach notification within 1 business day | IL-015 Phase 4

### Constructor

```python
# Production client (requires FCA env vars):
from services.recon.fca_regdata_client import FCARegDataClient
client = FCARegDataClient()
# Reads: FCA_REGDATA_URL, FCA_REGDATA_API_KEY, FCA_FIRM_REFERENCE from env

# Sandbox/test stub (no real API calls):
from services.recon.fca_regdata_client import MockFCARegDataClient
client = MockFCARegDataClient()
```

### `submit_breach_notification(breach: BreachRecord) → NotificationResult`

Submit a safeguarding breach to FCA RegData API.

```python
from services.recon.fca_regdata_client import MockFCARegDataClient
from services.recon.breach_detector import BreachRecord
from decimal import Decimal
from datetime import date

client = MockFCARegDataClient()
breach = BreachRecord(
    account_id="019d6332-f274-709a-b3a7-983bc8745886",
    account_type="client_funds",
    currency="GBP",
    discrepancy=Decimal("15000.00"),
    days_outstanding=4,
    first_seen=date(2026, 4, 7),
    latest_date=date(2026, 4, 10),
)
result = client.submit_breach_notification(breach)
# NotificationResult(success=True, fca_reference="FCA-SANDBOX-...", submitted_at="...")
```

### `NotificationResult` fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | True if submitted successfully |
| `fca_reference` | `str` | FCA-assigned reference number |
| `submitted_at` | `str` | ISO-8601 submission timestamp |
| `error` | `str \| None` | Error message if success=False |

---

## ReconAnalysisSkill

**Module:** `agents.compliance.skills.recon_analysis`
**FCA rule:** CASS 7.15 / CASS 15.12 — AI-assisted discrepancy classification | IL-015 Phase 5

### Constructor

```python
from agents.compliance.skills.recon_analysis import ReconAnalysisSkill

# Optionally provide historical data for SYSTEMATIC_ERROR detection:
skill = ReconAnalysisSkill(history={
    "account-001": [
        {"date": date(2026, 4, 8), "discrepancy": Decimal("500.00"), "status": "DISCREPANCY"},
    ]
})
```

### `analyze(results: list) → List[AnalysisReport]`

Classify each ReconResult.

```python
reports = skill.analyze(reconciliation_results)
for report in reports:
    print(f"{report.account_id}: {report.classification} (confidence={report.confidence})")
    # HITL gate: if report.confidence < Decimal("0.70") → compliance officer review
```

### `DiscrepancyClass` enum

| Value | Condition | Confidence |
|-------|-----------|------------|
| `MATCHED` | status == MATCHED | 1.00 |
| `FRAUD_RISK` | abs(discrepancy) > £50,000 | 0.95 |
| `SYSTEMATIC_ERROR` | 2+ consecutive DISCREPANCY days | 0.90 |
| `TIMING_DIFFERENCE` | abs(discrepancy) < £100 | 0.80 |
| `MISSING_TRANSACTION` | default | 0.75 |

### `AnalysisReport` fields (frozen dataclass)

| Field | Type | Description |
|-------|------|-------------|
| `account_id` | `str` | Midaz account UUID |
| `classification` | `DiscrepancyClass` | Classification label |
| `confidence` | `Decimal` | 0.00-1.00 (never float) |
| `recommendation` | `str` | Human-readable action |
| `pattern_detected` | `str` | Pattern description |

---

## BreachPredictionSkill

**Module:** `agents.compliance.skills.breach_prediction`
**FCA rule:** CASS 15.12 — early warning before breach threshold | IL-015 Phase 5

### `predict(account_id: str, history: list[dict]) → PredictionResult`

Predict breach probability using moving average trend.

```python
from agents.compliance.skills.breach_prediction import BreachPredictionSkill
from decimal import Decimal
from datetime import date

skill = BreachPredictionSkill()
history = [
    {"date": date(2026, 4, 8), "discrepancy": Decimal("500.00"), "status": "DISCREPANCY"},
    {"date": date(2026, 4, 9), "discrepancy": Decimal("800.00"), "status": "DISCREPANCY"},
    {"date": date(2026, 4, 10), "discrepancy": Decimal("1200.00"), "status": "DISCREPANCY"},
]
result = skill.predict("acct-001", history)
# PredictionResult(probability=Decimal("0.02"), trend="DETERIORATING", predicted_breach_in_days=0)
```

### `PredictionResult` fields (frozen dataclass)

| Field | Type | Description |
|-------|------|-------------|
| `account_id` | `str` | Midaz account UUID |
| `probability` | `Decimal` | 0.00-1.00 breach probability (never float) |
| `predicted_breach_in_days` | `int \| None` | Days until FCA breach (None = no breach) |
| `trend` | `str` | `"IMPROVING"` / `"STABLE"` / `"DETERIORATING"` |
| `confidence` | `Decimal` | Prediction confidence (more history = higher) |

---

## PaymentService

**Module:** `services.payment.payment_service`
**FCA rule:** FPS (CASS 6), SEPA (PSD2)

### Factory

```python
from services.payment.payment_service import build_payment_service

# Auto-selects adapter from PAYMENT_ADAPTER env var:
# PAYMENT_ADAPTER=mock   → MockPaymentAdapter (default, no API key)
# PAYMENT_ADAPTER=modulr → ModulrClient (requires MODULR_API_KEY)
service = build_payment_service()
```

### `send(intent: PaymentIntent) → PaymentResult`

Submit a payment. Always writes to `banxe.payment_events` audit log (even on FAILED).

```python
from decimal import Decimal
from services.payment.payment_port import PaymentIntent, PaymentRail

intent = PaymentIntent(
    idempotency_key="order-12345",        # unique per payment attempt
    rail=PaymentRail.FPS,                 # FPS | SEPA_CT | SEPA_INSTANT
    amount=Decimal("250.00"),             # Decimal only — never float (I-05)
    currency="GBP",                       # FPS=GBP, SEPA=EUR
    debtor_account_id="019d6332-...",
    creditor_iban="GB29NWBK60161331926819",
    creditor_name="Acme Ltd",
    reference="Invoice INV-001",
)
result = service.send(intent)
# PaymentResult(status=PaymentStatus.COMPLETED, ...)
```

### `PaymentIntent` validation rules

| Constraint | Rule |
|-----------|------|
| `amount` type | Must be `Decimal` — `TypeError` if float or int |
| FPS currency | Must be `GBP` |
| SEPA_CT / SEPA_INSTANT currency | Must be `EUR` |
| FPS limit | ≤ £1,000,000 per payment |
| SEPA_INSTANT limit | ≤ €100,000 per payment |

### `PaymentRail` enum

| Value | Settlement | Currency |
|-------|-----------|---------|
| `FPS` | Instant (< 20s) | GBP |
| `SEPA_INSTANT` | Instant (< 10s) | EUR |
| `SEPA_CT` | Next business day | EUR |

### `PaymentResult` fields

| Field | Type | Description |
|-------|------|-------------|
| `payment_id` | `str` | Provider reference ID |
| `status` | `PaymentStatus` | `COMPLETED` / `PROCESSING` / `FAILED` |
| `rail` | `PaymentRail` | Rail used |
| `amount` | `Decimal` | Amount settled |
| `currency` | `str` | ISO-4217 |
| `submitted_at` | `datetime` | UTC timestamp |
| `error_message` | `str \| None` | Set on FAILED |

---

## FIN060Generator

**Module:** `services.reporting.fin060_generator`
**FCA rule:** CASS 15 / PS25/12 — monthly FIN060 return, deadline 15th

### `generate_fin060(period_start: date, period_end: date) → Path`

Generate FIN060a/b PDF. Returns path to generated file.

```python
from datetime import date
from services.reporting.fin060_generator import generate_fin060

pdf_path = generate_fin060(
    period_start=date(2026, 3, 1),
    period_end=date(2026, 3, 31),
)
# Returns: Path("/data/banxe/reports/fin060/FIN060_202603.pdf")
```

**Requires:** `clickhouse-driver` + `weasyprint` installed.
**Output dir:** `FIN060_OUTPUT_DIR` env var (default `/data/banxe/reports/fin060`).

---

## TransactionMonitorRouter

**Module:** `api.routers.transaction_monitor`
**FCA rule:** MLR 2017 — AML/CTF screening | IL-071
**Prefix:** `/monitor`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/monitor/health` | Service health |
| `POST` | `/monitor/score` | Score a transaction for AML risk → `RiskScore` + optional `AMLAlert` |
| `GET` | `/monitor/alerts` | List alerts (filter: severity, status, customer_id) |
| `GET` | `/monitor/alerts/{alert_id}` | Get alert detail |
| `PATCH` | `/monitor/alerts/{alert_id}` | Update alert status (HITL gate: CRITICAL+CLOSED requires notes) |
| `GET` | `/monitor/velocity/{customer_id}` | Velocity metrics for customer (1h/24h/7d windows) |
| `GET` | `/monitor/metrics` | Dashboard metrics (counts by severity/status) |
| `POST` | `/monitor/backtest` | Backtest scoring rules against historical transactions |

### Score Transaction

```python
POST /monitor/score
{
    "transaction_id": "tx-001",
    "customer_id": "cust-001",
    "amount": "9500.00",   # Decimal string (I-01)
    "currency": "GBP",
    "jurisdiction": "GB",
    "counterparty_jurisdiction": "GB",
    "is_crypto": false
}
# → {"risk_score": {...}, "alert": {...} | null}
```

**Risk scoring formula:** rules 40% + ML 30% + velocity 30%
**CRITICAL threshold:** ≥ 0.90 | **HIGH:** ≥ 0.75 | **MEDIUM:** ≥ 0.50

### HITL gate on PATCH /alerts/{id}

| Case | Allowed |
|------|---------|
| Any status → REVIEWING | Always allowed |
| MEDIUM/HIGH → CLOSED | Allowed without notes |
| CRITICAL → CLOSED | **Requires `reviewer_notes` field** (I-27) |

---

## ComplianceKBRouter

**Module:** `api.routers.compliance_kb`
**FCA rule:** FCA CASS 15, MLR 2017, PS22/9 — AI-assisted compliance guidance | IL-069
**Prefix:** `/v1/kb`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/kb/health` | Service health |
| `GET` | `/v1/kb/notebooks` | List regulatory notebooks |
| `GET` | `/v1/kb/notebooks/{id}` | Get notebook detail |
| `POST` | `/v1/kb/query` | RAG query across all notebooks |
| `POST` | `/v1/kb/search` | Semantic search within a notebook |
| `POST` | `/v1/kb/compare` | Compare two regulation versions |
| `POST` | `/v1/kb/ingest` | Ingest a new PDF into a notebook |
| `GET` | `/v1/kb/citations/{id}` | Get citations for a source |

---

## ExperimentsRouter

**Module:** `api.routers.experiments`
**FCA rule:** I-27 — supervised AI changes | IL-070
**Prefix:** `/v1/experiments`

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/experiments/design` | Design new compliance experiment (DRAFT) |
| `GET` | `/v1/experiments/list` | List experiments (filter by status) |
| `GET` | `/v1/experiments/{id}` | Get experiment detail |
| `PATCH` | `/v1/experiments/{id}/approve` | Approve experiment (DRAFT→ACTIVE) |
| `PATCH` | `/v1/experiments/{id}/reject` | Reject experiment |
| `GET` | `/v1/experiments/metrics/current` | Current AML baseline metrics |
| `POST` | `/v1/experiments/{id}/propose` | Propose change (dry_run=True default, I-27) |
| `GET` | `/v1/experiments/{id}/audit` | Experiment audit trail |

---

## MCP Tools Registry

**Module:** `banxe_mcp/server.py`
**Transport:** stdio (MCP protocol)
**Total tools:** 34

### Financial Tools
| Tool | Description |
|------|-------------|
| `get_account_balance(account_id)` | Midaz balance |
| `list_accounts()` | All org accounts |
| `get_transaction_history(account_id, period)` | Transaction history |
| `get_kyc_status(customer_id)` | KYC status |
| `check_aml_alert(transaction_id)` | AML check |
| `get_exchange_rate(from_currency, to_currency)` | Frankfurter ECB FX |
| `get_payment_status(payment_id)` | Payment status |
| `get_recon_status(recon_date)` | Reconciliation status |
| `get_breach_history(account_id, days)` | CASS 15 breach history |
| `get_discrepancy_trend(account_id, days)` | Discrepancy trend |
| `run_reconciliation(recon_date, dry_run)` | Trigger reconciliation |

### Agent Routing Layer (IL-ARL-01)
| Tool | Description |
|------|-------------|
| `route_agent_task(task, context, priority)` | Route to Tier 1/2/3 LLM |
| `query_reasoning_bank(query, context_type)` | Reasoning bank query |
| `get_routing_metrics(hours)` | Routing stats |
| `manage_playbooks(action, playbook_id)` | Playbook CRUD |

### Design System (IL-ADDS-01)
| Tool | Description |
|------|-------------|
| `generate_component(component_name, variant)` | Mitosis → React |
| `sync_design_tokens(file_id)` | Penpot token sync |
| `visual_compare(component_a, component_b)` | Visual diff |
| `list_design_components(file_id)` | Component catalog |

### Compliance KB (IL-069)
| Tool | Description |
|------|-------------|
| `kb_list_notebooks(tags, jurisdiction)` | List notebooks |
| `kb_get_notebook(notebook_id)` | Notebook detail |
| `kb_query(question, jurisdiction, top_k)` | RAG query |
| `kb_search(notebook_id, query, limit)` | Semantic search |
| `kb_compare_versions(notebook_id, v1, v2)` | Version compare |
| `kb_get_citations(source_id, notebook_id)` | Citations |

### Transaction Monitor (IL-071)
| Tool | Description |
|------|-------------|
| `monitor_score_transaction(tx_event)` | AML score |
| `monitor_get_alerts(severity, status, customer_id)` | Alert list |
| `monitor_get_alert_detail(alert_id)` | Alert detail |
| `monitor_get_velocity(customer_id)` | Velocity metrics |
| `monitor_dashboard_metrics()` | Dashboard |

### Experiment Copilot (IL-070)
| Tool | Description |
|------|-------------|
| `experiment_design(objective, baseline_metrics)` | Design experiment |
| `experiment_list(status)` | List experiments |
| `experiment_get_metrics(period_days)` | AML metrics |
| `experiment_propose_change(exp_id, change_type, rationale)` | Propose change |

---

## CLI Entry Points

### Daily Reconciliation

```bash
python3 -m services.recon.midaz_reconciliation \
  [--date YYYY-MM-DD]   # default: today
  [--dry-run]            # no CH writes, no alerts
  [--json]               # JSON output to stdout

# Exit codes:
# 0 = all MATCHED
# 1 = at least one DISCREPANCY
# 2 = at least one PENDING
# 3 = fatal error
```

---

## Test Stubs (for unit tests)

```python
# InMemoryReconClient — replaces ClickHouseReconClient in tests
from services.recon.clickhouse_client import InMemoryReconClient
ch = InMemoryReconClient()
ch.events          # List[dict] of all INSERT params
ch.breaches        # List[dict] of breach inserts only
ch.call_count      # total INSERT count
ch.reset()         # clear log

# StubLedgerAdapter — replaces MidazLedgerAdapter in tests
from services.ledger.midaz_adapter import StubLedgerAdapter
ledger = StubLedgerAdapter({"account-uuid": Decimal("50000.00")})

# MockPaymentAdapter — replaces ModulrClient in tests
from services.payment.mock_payment_adapter import MockPaymentAdapter
adapter = MockPaymentAdapter(failure_rate=0.0)
adapter.payments   # dict of idempotency_key → PaymentResult
adapter.reset()
```
