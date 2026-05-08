# SESSION-2026-05-09 — Sprint 6 Start Canon

**Date:** 2026-05-09  
**Phase:** Sprint 6 — Production Wiring + Wave B OTP Delivery Port  
**Branch:** `docs/sprint-6-start-canon-2026-05-09`  
**Upstream PRs merged:** Phase 5 tranche 5 #92 — all closed; roadmap PR #60 100% complete

---

## Roadmap Status (as of 2026-05-09)

| Phase | Waves | PRs | Tests | Status |
|-------|-------|-----|-------|--------|
| Phase 4 — Migration | Wave A–E | #74–#88 | ~554 | ✅ 100% closed |
| Phase 5 — Consolidation | Tranches 1–5 | #89–#92 | +108 | ✅ 100% closed |
| **Total green** | — | — | **9526 passed, 5 skipped** | ✅ |

**Roadmap PR #60** (BANXE.RAR → EMI Smart Refactor) — **closed 100%**.  
**FCA CASS 15 / PS25/12 deadline 7 May 2026** — delivered on time.

---

## Frozen Port Contracts (9 total — FROZEN as of 2026-05-08)

Reference: `docs/phase5/PORT-CONTRACTS-FREEZE-2026-05-08.md`

| Port | File | Wave |
|------|------|------|
| `TokenManagerPort` | `services/auth/token_manager_port.py` | A |
| `IAMPort` | `services/auth/` | A |
| `TwoFactorPort` | `services/auth/two_factor_port.py` | B |
| `ScaServicePort` | `services/auth/sca_service_port.py` | B |
| `OtpDeliveryPort` | `services/auth/otp_delivery_port.py` | B |
| `PaymentRailPort` | `services/payment/payment_port.py` | C |
| `KYCWorkflowPort` | `services/kyc/kyc_port.py` | D |
| `CryptoLedgerPort` | `services/ledger/crypto_ledger_port.py` | E |
| `CryptoRpcPort` | `services/ledger/crypto_ledger_port.py` | E |

**Invariant:** Frozen port signatures are read-only. Any signature change requires a new ADR + minor version bump. Breaking changes reviewed in a separate PR.

---

## Production Wiring Backlog (Sprint 6 scope)

Reference: `docs/phase5/RELEASE-NOTES-PHASE-5-2026-05-08.md` §"What Is NOT Done"

| Ticket | Stub | File | Required env vars |
|--------|------|------|-------------------|
| IL-OTP-PROD-01 | `TwilioOtpStub` | `services/auth/production/twilio_otp_stub.py` | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` |
| IL-OTP-PROD-02 | `SendGridOtpStub` | `services/auth/production/twilio_otp_stub.py` | `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`, `SENDGRID_OTP_TEMPLATE_ID` |
| IL-SEPA-PROD-01 | `ModulrSepaStub` | `services/payment/production/modulr_sepa_stub.py` | `MODULR_API_KEY`, `MODULR_BASE_URL` |
| IL-CRYPTO-PROD-01 | `MidazCryptoStub` | `services/ledger/production/midaz_crypto_stub.py` | `MIDAZ_API_KEY`, `MIDAZ_LEDGER_URL` |
| IL-KYC-PROD-01 | `SumsubHttpStub` | `services/compliance/production/sumsub_http_stub.py` | `SUMSUB_APP_TOKEN`, `SUMSUB_SECRET_KEY`, `SUMSUB_BASE_URL` |

All stubs raise `NotImplementedError` — no network I/O in dev/test. Protocol conformance tested in `tests/test_production_stubs.py` (11 tests).

---

## Sprint 6 Open Items

### Wave B — OTP Delivery Port (active branch)

**Branch:** `sprint5/wave-b-otp-delivery-port-2026-05-07`  
**Status:** Port frozen; `LegacyOtpAdapter` green; `TwilioOtpStub` / `SendGridOtpStub` stubs placed.

Remaining for full Wave B production closure:
- `LegacyScaAdapter` + `OtpDeliveryPort` integration path (via `SCAService`): verify `send_otp` → `verify_otp` round-trip is wired in `AuthApplicationService`
- Redis adapter for OTP store durability (deferred per ADR-029 §Consequences; planned Wave C+)
- Production adapters (IL-OTP-PROD-01, IL-OTP-PROD-02) — separate PRs, require sandbox integration tests

### Auth Refactor (AUTH_REFACTOR_TASKS.md)

Phases A/B/C remain partially open:
- Phase A: mark inline JWT locations and IAM operation boundaries — `api/routers/auth.py` verified thin; token_manager seam confirmed
- Phase B: `AuthApplicationService` boundary extraction complete; IAM through `IAMPort` wired; SCA transport branching in router still present
- Phase C: adapter seams for BANXE.RAR auth token logic and IAM logic — locked until Wave A adapters fully validated in staging

Import discipline governed by `AUTH_IMPORT_ORDER.md`:
1. Router stays thin (transport only)
2. Token issuance/refresh through `TokenManagerPort`
3. IAM through `IAMPort`
4. SCA through `ScaServicePort` / `SCAService`
5. OTP through `OtpDeliveryPort` / `LegacyOtpAdapter`

---

## Canon Active (Sprint 6)

| Document | Status | Rule |
|----------|--------|------|
| ADR-025 Agent Interaction Canon | ACCEPTED | OCAT, single-addressee, no confirmation on safe commands |
| ADR-026 Guardian agent.bash | ACCEPTED | CB1-deny-path / CB2-secret-leak / CB3-frozen-sandbox / CB4-dangerous-cmd |
| ADR-029 OtpDeliveryPort | Proposed → FROZEN | 4-method Protocol, `@runtime_checkable`, `LegacyOtpAdapter` REWRITE-1 |
| PORT-CONTRACTS-FREEZE-2026-05-08 | FROZEN | 9 ports locked; signature change → new ADR + minor bump |
| AUTH_IMPORT_ORDER | Active | 5-step import discipline for `services/auth/` |
| AUTH_MATRIX | Reference | Component → port boundary map for Sprint 6 auth refactor |

---

## Architecture Invariants (all active)

| ID | Rule | Enforced by |
|----|------|-------------|
| I-01 | `Decimal` only for monetary amounts | Semgrep `banxe-float-money` |
| I-02 | Jurisdiction block: RU/BY/IR/KP/CU/MM/AF/VE/SY | `_jurisdictions.py` + SEPA adapter |
| I-04 | EDD threshold: £10k individual / £50k corporate | `_edd.py` + SumSub/BinanceKYC |
| I-08 | ClickHouse TTL ≥ 5 years | Semgrep `banxe-clickhouse-ttl-reduce` |
| I-24 | Append-only audit trail — `BaseAuditRecord` frozen | `services/_legacy_common/audit.py` |
| I-27 | HITL — MLRO sign-off required for EDD approval | `SumsubHttpStub.approve_edd` docstring gate |

---

## Transport Drops Completed (ADR-025 §15-16)

| Transport | Replaced by |
|-----------|-------------|
| gRPC (all services) | In-memory adapters |
| TypeORM repositories | Frozen Pydantic models + in-memory dicts |
| NestJS DI / EventEmitter | Constructor injection / Protocol DI |
| GCP Bifrost XML | In-memory stub; `ModulrSepaStub` planned |
| RabbitMQ publishers | No event bus in scope; ClickHouse audit log |
| Redis cron (OTP expiry) | In-memory TTL; Redis adapter planned |
| Amplitude analytics | Removed (not FCA-regulated) |

---

## Sandbox-Priority Canon (Sprint 6+)

All integration tests must run against sandboxes — no live money, no real KYC, no real OTPs in CI:

| Vendor | Sandbox entry point | Auth |
|--------|--------------------|----|
| Twilio | Twilio sandbox (magic numbers) | `TWILIO_ACCOUNT_SID` test credentials |
| SendGrid | SendGrid sandbox mode | `SENDGRID_SANDBOX=true` header |
| Modulr | Modulr sandbox `api.modulrfinance.io/v1-sandbox` | `MODULR_API_KEY` test key |
| Midaz | Midaz local docker or `staging.midaz.io` | `MIDAZ_API_KEY` staging |
| SumSub | SumSub sandbox applicant fixtures | `SUMSUB_APP_TOKEN` test |

---

## Quality Gate Baseline (2026-05-09)

```
ruff check .                → 0 issues
semgrep banxe-rules.yml     → 0 findings
pytest tests/               → 9526 passed, 5 skipped
bandit -r -ll services/*/production/ → 0 Medium/High
```

Pre-commit hooks: Ruff ✅ Bandit ✅ Semgrep ✅ Pytest ✅ Biome ✅ Gitleaks ✅
