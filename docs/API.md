# API Reference — Banxe EMI Analytics Stack

**Version:** 0.7.0 | **Updated:** 2026-04-07 | IL-017

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
