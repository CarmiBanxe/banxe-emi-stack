# Finance Domain Summary — banxe-emi-stack
# Source: services/ledger, recon, reporting, payment analysis
# Created: 2026-04-10
# Migration Phase: 4
# Purpose: Financial services domain map

## Financial services overview

Banxe operates as an FCA-authorised EMI under CASS 15 / PS25/12.
All financial operations enforce: Decimal-only (I-01), audit trail (I-24), no sanctions (I-02).

## Core financial modules

### Ledger (services/ledger/ — 3 files)
- **CBS**: Midaz (:8095) — primary core banking system
- `midaz_client.py` — async API client (httpx)
- `midaz_adapter.py` — sync wrapper + stub adapter
- Operations: `create_tx()`, `get_balance()` via LedgerPort (I-28)
- Decimal-only amounts, no float

### Reconciliation (services/recon/ — 10 files)
- **FCA**: CASS 7.15 daily safeguarding reconciliation
- `reconciliation_engine.py` — MATCHED/DISCREPANCY/PENDING logic
- `statement_fetcher.py` — CSV + CAMT.053 bank statement reader
- `bankstatement_parser.py` — ISO20022 CAMT.053 + MT940 parser
- `statement_poller.py` — adorsys PSD2 auto-pull (FA-07)
- `breach_detector.py` — DISCREPANCY streak ≥3 days → FCA alert
- `clickhouse_client.py` — audit trail writer (append-only)
- `midaz_reconciliation.py` — full pipeline CLI (--date, --dry-run, --json)
- `cron_daily_recon.py` — systemd service entrypoint
- `mock_aspsp.py` — mock bank for sandbox testing
- Threshold: £1.00 (configurable via RECON_THRESHOLD_GBP)
- Exit codes: 0=MATCHED, 1=DISCREPANCY, 2=PENDING, 3=FATAL

### Reporting (services/reporting/ — 3 files)
- **FCA**: CASS 15.12.4R — monthly FIN060 safeguarding return
- `fin060_generator.py` — WeasyPrint PDF generation (FIN060a/b)
- `regdata_return.py` — FCA RegData submission
- dbt models: `fin060_monthly.sql`, `safeguarding_daily.sql`
- Deadline: 15th of month following reporting period
- Sign-off: CFO/MLRO required before submission

### Payments (services/payment/ — 7 files)
- **FCA**: PSR 2017 — payment services regulations
- `payment_port.py` — PaymentRailPort protocol, PaymentIntent/Result
- `modulr_client.py` — Modulr REST adapter (FPS, SEPA CT/Instant, BACS)
- `mock_payment_adapter.py` — mock adapter for testing
- `payment_service.py` — limits enforcement (FPS £1M, SEPA Instant €100k)
- `webhook_handler.py` — FastAPI router, HMAC-SHA256 verify
- `openapi.yml` — OpenAPI 3.1 spec for webhook handler
- Status: Mock adapter active; Modulr blocked on BT-001 (CEO registration)

## Financial data stores

| Store | Engine | Table(s) | Retention | Write policy |
|-------|--------|----------|-----------|-------------|
| Safeguarding events | ClickHouse | `banxe.safeguarding_events` | 5yr (I-08) | Append-only (I-24) |
| Safeguarding breaches | ClickHouse | `banxe.safeguarding_breaches` | 5yr | Append-only |
| Payment events | ClickHouse | `banxe.payment_events` | 5yr | Append-only |
| Financial audit trail | PostgreSQL | pgAudit logs | 5yr | Write + DDL logged |
| FX rates | Frankfurter | In-memory (ECB data) | — | Read-only |

## FCA compliance coverage

| FCA requirement | Implementation | Status |
|-----------------|---------------|--------|
| CASS 7.15.17R — daily reconciliation | systemd timer 07:00 UTC Mon-Fri | ✅ Active |
| CASS 7.15.29R — investigate discrepancy in 1 day | n8n MLRO alert on exit code 1 | ✅ Active |
| CASS 15.12.4R — monthly FIN060 return | fin060_generator.py + RegData | ✅ (manual upload) |
| PSR 2017 — payment limits | PaymentService with config-as-data | ✅ (mock adapter) |
| I-08 — 5yr audit retention | ClickHouse TTL enforced in schema | ✅ |
| I-24 — append-only audit | Semgrep rule blocks DELETE/UPDATE | ✅ |
| I-01 — no float for money | Decimal-only, Pydantic validators | ✅ |

## Financial products

| Product | Currencies | Payment rails | Status |
|---------|------------|--------------|--------|
| EMI Account | GBP, EUR, USD | FPS, BACS, SEPA CT, SEPA Instant | Active (mock) |
| Business Account | GBP, EUR, USD, CHF | FPS, BACS, SEPA CT, SEPA Instant | Active (mock) |
| FX Account | 8 currencies | FPS, SEPA CT, SEPA Instant | Active (mock) |
| Prepaid Card | GBP, EUR | FPS (top-up), Card payment | Active (mock) |

---
*Last updated: 2026-04-10 (Phase 4 migration)*
