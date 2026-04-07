# CHANGELOG — Banxe EMI Analytics Stack

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) + [Semantic Versioning](https://semver.org/).

Format: `## [version] — YYYY-MM-DD` | IL reference | FCA rule

---

## [0.7.0] — 2026-04-07 · IL-017
### Added
- `CHANGELOG.md`, `docs/RUNBOOK.md`, `docs/ONBOARDING.md`, `docs/API.md`
- `services/payment/openapi.yml` — OpenAPI 3.1 spec for Modulr webhook handler
- `banxe-architecture/docs/DOC-STANDARD.md` — documentation canon (I-29)

---

## [0.6.0] — 2026-04-07 · IL-016
### Added
- `scripts/quality-gate.sh` — unified quality gate (semgrep + ruff + pytest + coverage + invariants)
- `.claude/agents/qualityguard-agent.md` — QualityGuard Agent definition
- `.claude/hooks/quality_gate_hook.py` — PreToolUse:Bash hook, blocks git commit on FAIL
- `.semgrep/banxe-rules.yml` — 2 new rules: `banxe-audit-delete` (I-24), `banxe-clickhouse-ttl-reduce` (I-08) → 10 total
- `banxe-architecture/docs/PLANES.md` — Developer / Product / Standby plane architecture

---

## [0.5.0] — 2026-04-07 · IL-015 · FCA CASS 15.12
### Added
- `services/recon/breach_detector.py` — BreachDetector: DISCREPANCY streak ≥ 3 days → write to `safeguarding_breaches` + n8n FCA alert
- `services/recon/clickhouse_client.py` — `write_breach()`, `get_discrepancy_streak()`, `get_latest_discrepancy()`; `InMemoryReconClient.breaches` property
- `scripts/monthly-fin060.sh` — FIN060 PDF cron wrapper (1st of month, deadline 15th)
- `tests/test_breach_detector.py` — 12 tests (no-breach cases, breach triggered, n8n alert, InMemoryReconClient)
- `tests/test_fin060.py` — 10 tests (FIN060Data, _build_html, generate_fin060 smoke, zero-rows fallback)
### Changed
- `services/recon/midaz_reconciliation.py` — step 5: call `BreachDetector.check_and_escalate()` after day-1 alerts
- `COMPLIANCE-MATRIX.md` S9-09: 43% → 75%
### Metrics
- Tests: 75/75 | Coverage: 80% | FCA S9-09: 75%

---

## [0.4.0] — 2026-04-07 · IL-014 (quality sprint)
### Fixed
- `services/config.py` — centralised env vars (eliminated duplication in clickhouse_client + fin060_generator)
- `services/recon/reconciliation_engine.py` — extracted `_pending_result()` static method
- `services/recon/statement_poller.py` — IBAN guard before `mkdir` (PermissionError fix)
### Added
- `tests/test_parsers_and_poller.py` — 18 tests (bankstatement_parser, poller, config)
### Metrics
- Ruff: 24 → 0 issues | Coverage: 74.3% → 80.0% | Tests: 51/51

---

## [0.3.0] — 2026-04-07 · IL-014 · Payment Rails
### Added
- `services/payment/payment_port.py` — `PaymentRailPort` Protocol, `PaymentIntent`, `PaymentResult` dataclasses; rail↔currency validation; `PaymentStatus` enum
- `services/payment/modulr_client.py` — Modulr REST adapter: FPS (`type: SCAN`), SEPA CT/Instant (`type: IBAN`); pence↔Decimal; HMAC-SHA256 webhook verify
- `services/payment/mock_payment_adapter.py` — `MockPaymentAdapter`: FPS/SEPA_INSTANT → COMPLETED; SEPA_CT → PROCESSING; idempotent
- `services/payment/payment_service.py` — `PaymentService`: FPS limit £1M, SEPA Instant €100k; audit trail on FAILED (I-24); `build_payment_service()` factory
- `services/payment/webhook_handler.py` — FastAPI router; HMAC-SHA256 guard; audit write non-blocking
- `scripts/schema/clickhouse_payments.sql` — `payment_events` (Decimal(18,2), TTL 5Y) + `mv_payment_daily_volume`
- `tests/test_payment_service.py` — 20 tests
### Notes
- Switch to real Modulr: `PAYMENT_ADAPTER=modulr MODULR_API_KEY=<key>` — zero code changes

---

## [0.2.0] — 2026-04-06 · IL-013 · D-recon + J-audit
### Added
- `services/ledger/midaz_adapter.py` — `MidazLedgerAdapter` (sync wrapper, `asyncio.run()`); `StubLedgerAdapter`
- `services/recon/reconciliation_engine.py` — `ReconciliationEngine`: MATCHED/DISCREPANCY/PENDING; £1.00 threshold (CEO Q3 decision)
- `services/recon/clickhouse_client.py` — `ClickHouseReconClient` + `InMemoryReconClient`; DDL: `safeguarding_events` + `safeguarding_breaches`
- `services/recon/midaz_reconciliation.py` — full pipeline CLI (`--date`, `--dry-run`, `--json`); exit codes 0/1/2/3
- `services/recon/statement_fetcher.py` — `StatementFetcher` (CSV + CAMT.053)
- `services/recon/statement_poller.py` — adorsys PSD2 poller (Phase 0 sandbox)
- `services/recon/bankstatement_parser.py` — CAMT.053 + MT940 parser; `IBAN_TO_ACCOUNT_ID` map
- `scripts/daily-recon.sh` — cron wrapper; cron: `0 7 * * 1-5` on GMKtec
- `dbt/` — 3 models (stg_ledger_transactions, stg_safeguarding_events, mart_safeguarding_daily); `sources.yml`
- `tests/test_reconciliation.py` — 13 tests
### Fixed
- Bearer header: empty `MIDAZ_TOKEN` → no Authorization header (httpx fix)
- Schema alignment with GMKtec: `event_time DateTime64(3)`, `Decimal(18,2)`

---

## [0.1.0] — 2026-04-06 · IL-009..IL-011 · P0 Skeleton
### Added
- Project scaffold: `services/`, `tests/`, `scripts/`, `dbt/`, `docs/`
- `services/reporting/fin060_generator.py` — FIN060a/b PDF (WeasyPrint); `FIN060Data` dataclass
- `scripts/deploy-recon-stack.sh`, `scripts/deploy-psd2-gateway.sh`
- Initial ClickHouse schema, dbt project skeleton
- `QUALITY.md` — quality tracking

---

*Maintained by: Claude Code (Developer Plane) | FCA CASS 15 / PS25/12*
