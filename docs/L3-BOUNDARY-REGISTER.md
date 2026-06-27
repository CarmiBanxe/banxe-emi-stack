# L3 Boundary Register — BANXE EMI Stack

**Generated:** 2026-06-27  
**IL:** IL-SP-L3DOC-2026-06-27 (TBD number — assign via Redis allocator on evo1)  
**Reference:** ADR-117 (Factory perimeter), ADR-025 §15-16 (Port contracts frozen), ADR-031 (Crypto staging)

---

## What is an L3 Boundary?

An **L3 boundary** is an intentional production seam in the codebase where a stub class or `raise NotImplementedError` marks the injection point for real credentials, external provider APIs, or Wave E/F production adapters. They are **NOT bugs or incomplete code** — they are the correct sandbox pattern per ADR-117.

Classifying L3 boundaries prevents future audits (FCA, MLRO, CTIO) from miscounting them as tech debt or architectural debt. This register is the single source of truth.

---

## Boundary Registry

| # | Service | File | Class / Method | Line | Type | Status | BT | GAP | Owner | Notes |
|---|---------|------|----------------|------|------|--------|----|-----|-------|-------|
| 1 | ledger | `services/ledger/production/midaz_crypto_stub.py` | `MidazCryptoStub.get_balance()` | 44 | L3-intentional | Wave E P3 | — | GAP-089 | CTIO | Production seam: crypto ledger ops via Midaz REST API |
| 2 | ledger | `services/ledger/production/midaz_crypto_stub.py` | `MidazCryptoStub.create_wallet_address()` | 55 | L3-intentional | Wave E P3 | — | GAP-089 | CTIO | Requires MIDAZ_API_KEY + MIDAZ_LEDGER_URL |
| 3 | ledger | `services/ledger/production/midaz_crypto_stub.py` | `MidazCryptoStub.create_tx()` | 65 | L3-intentional | Wave E P3 | — | GAP-089 | CTIO | Idempotent on tx_id; production impl tagged [IL-CRYPTO-PROD-01] |
| 4 | ledger | `services/ledger/production/midaz_crypto_stub.py` | `MidazCryptoStub.get_fee_estimate()` | 76 | L3-intentional | Wave E P3 | — | GAP-089 | CTIO | Fee estimation from Midaz pricing tables (RPC in Wave F) |
| 5 | ledger | `services/ledger/production/midaz_crypto_stub.py` | `MidazCryptoStub.health()` | 83 | L3-intentional | Wave E P3 | — | GAP-089 | CTIO | Liveness probe against Midaz API |
| 6 | ledger | `services/ledger/legacy/legacy_crypto_wallet_adapter.py` | `LegacyCryptoWalletAdapter.create_tx()` | 127 | L3-intentional | Delegation hint | — | GAP-089 | CTIO | Explicit hint: delegate to LegacyCryptoProcessingAdapter (REWRITE-8 scope) |
| 7 | ledger | `services/ledger/legacy/legacy_crypto_wallet_adapter.py` | `LegacyCryptoWalletAdapter.get_fee_estimate()` | 136 | L3-intentional | Delegation hint | — | GAP-089 | CTIO | Explicit hint: delegate to LegacyCryptoProcessingAdapter (REWRITE-8 scope) |
| 8 | ledger | `services/ledger/legacy/legacy_crypto_processing_adapter.py` | `LegacyCryptoProcessingAdapter.get_balance()` | 162 | L3-intentional | Delegation hint | — | GAP-089 | CTIO | Explicit hint: delegate to LegacyCryptoWalletAdapter (REWRITE-7 scope) |
| 9 | ledger | `services/ledger/legacy/legacy_crypto_processing_adapter.py` | `LegacyCryptoProcessingAdapter.create_wallet_address()` | 169 | L3-intentional | Delegation hint | — | GAP-089 | CTIO | Explicit hint: delegate to LegacyCryptoWalletAdapter (REWRITE-7 scope) |
| 10 | payment | `services/payment/production/modulr_sepa_stub.py` | `ModulrSepaStub.submit_payment()` | 31 | L3-intentional | Wave C P2 | BT-001/004 | — | CTIO | Production seam: SEPA payment submission via Modulr Finance REST API |
| 11 | payment | `services/payment/production/modulr_sepa_stub.py` | `ModulrSepaStub.get_payment_status()` | 38 | L3-intentional | Wave C P2 | BT-001/004 | — | CTIO | Async status updates via webhook handler (services/payment/webhook_handler.py) |
| 12 | payment | `services/payment/production/modulr_sepa_stub.py` | `ModulrSepaStub.health()` | 45 | L3-intentional | Wave C P2 | BT-001/004 | — | CTIO | Liveness probe against Modulr API |
| 13 | compliance | `services/compliance/production/sumsub_http_stub.py` | `SumsubHttpStub.create_workflow()` | 39 | L3-intentional | Wave D P1 | BT-001/004 | — | CTIO | Production seam: KYC workflow via SumSub REST API (HMAC-signed) |
| 14 | compliance | `services/compliance/production/sumsub_http_stub.py` | `SumsubHttpStub.get_workflow()` | 46 | L3-intentional | Wave D P1 | BT-001/004 | — | CTIO | Query applicant status; I-27 HITL gate required for approval |
| 15 | compliance | `services/compliance/production/sumsub_http_stub.py` | `SumsubHttpStub.submit_documents()` | 52 | L3-intentional | Wave D P1 | BT-001/004 | — | CTIO | Document submission to SumSub; requires sandbox integration tests |
| 16 | compliance | `services/compliance/production/sumsub_http_stub.py` | `SumsubHttpStub.approve_edd()` | 58 | L3-intentional | Wave D P1 | BT-001/004 | — | CTIO | MLRO approval gate (I-27) enforced before calling this method |
| 17 | compliance | `services/compliance/production/sumsub_http_stub.py` | `SumsubHttpStub.reject_workflow()` | 65 | L3-intentional | Wave D P1 | BT-001/004 | — | CTIO | Workflow rejection with structured reason; audit trail (I-24) required |
| 18 | compliance | `services/compliance/production/sumsub_http_stub.py` | `SumsubHttpStub.health()` | 71 | L3-intentional | Wave D P1 | BT-001/004 | — | CTIO | Liveness probe against SumSub API |
| 19 | auth | `services/auth/production/twilio_otp_stub.py` | `TwilioOtpStub.send_otp()` | 44 | L3-intentional | Wave C P1 | BT-001/004 | — | CTIO | Production seam: SMS OTP delivery via Twilio Verify / Messaging API |
| 20 | auth | `services/auth/production/twilio_otp_stub.py` | `SendGridOtpStub.send_otp()` | 73 | L3-intentional | Wave C P1 | BT-001/004 | — | CTIO | Production seam: email OTP delivery via SendGrid Dynamic Templates |
| 21 | api | `api/deps.py` | `get_webhook_reliability_port()` | 397 | L2-pending | Driver code | — | — | DevOps | DI fallback for unrecognized WEBHOOK_RELIABILITY_ADAPTER env value; no external blocker |
| 22 | safeguarding-engine | `services/safeguarding-engine/app/integrations/bank_api_client.py` | Comments reference BT-015 (P1) | — | BT-blocked | Phase 3.6 P1 | BT-015 | — | CTIO | Bank API integration deferred (returns stubs, not NotImplementedError) |

---

## Classification Rationale

### L3-intentional (20 entries)
**Correct sandbox pattern. No action needed.**

Production stub classes that satisfy their Port/Protocol structurally but raise `NotImplementedError` on network-touching methods. Each stub:
- Lives in `services/*/production/` or `services/*/legacy/` (marked by module name).
- Has detailed docstrings naming the required env vars, Package deps, and integration test strategy.
- Points to a dedicated production PR tag for implementation (e.g., `[IL-OTP-PROD-01]`, `[IL-CRYPTO-PROD-01]`).
- Is used in DI layer (`api/deps.py`) with conditional wiring based on env var or feature flags.

**These are correct by design. Auditors should skip them.**

### BT-blocked (6 entries in this register; live in code as comments)
**External credential/spec awaiting owner action. Documented in "Pending BT" section below.**

Stubs in the production/ dirs that cannot be tested without external provider credentials, API specs, or sandbox access. These are tracked by BT numbers and linked to owners (CTIO, CEO/CFO).

### L2-pending (1 entry: api/deps.py:397)
**Genuine code gap. No external blocker; should be implemented if webhook_reliability_adapter extensibility is desired.**

The NotImplementedError in `get_webhook_reliability_port()` is a defensive fallback. No invariant requires extensibility here; the function is called only with known values ("in_memory", "redis"). Implementing this would add a plugin system, which is out-of-scope for P0. Current approach (fail loudly) is acceptable.

---

## Resolved BT Blockers (Closed, Not Tech Debt)

These BT items are **resolved** and documented here to prevent future audits from reopening them as open blockers.

| BT | Description | Resolution | Date | Evidence |
|----|-------------|-----------|------|----------|
| BT-002 | Companies House live PSC API feed | Resolved — adapter implemented (KYB Wave B) | 2026-05-15 | `services/kyb_onboarding/companies_house_adapter.py:67` (docstring marks resolved) |
| BT-004 | Provider registry — zero-code provider switching | Resolved — registry operational (P0 Wave A) | 2026-05-01 | `services/providers/provider_registry.py:17` (enables switching via PAYMENT_ADAPTER etc.) |
| BT-005 | PS22/9 Consumer Duty live reporting (fx_compliance_reporter) | Resolved → HITL gate (I-27 PROPOSES, never auto-applies) | 2026-06-01 | `services/fx_engine/fx_compliance_reporter.py:98` (returns HITL proposal, fails closed) |
| BT-006 | FCA RegData fin060_generator_v2 — live submission | Resolved → HITL gate via ReturnsGovernor (I-27) | 2026-06-15 | `api/deps.py:295–310` (RegDataGabrielAdapter wiring under GABRIEL_ADAPTER=regdata) |
| BT-012 | HMRC Gateway (FATCA/CRS) — live reporter | Resolved — returns HITL proposal (I-27, never auto-submits) | 2026-06-01 | `services/fatca_crs/hmrc_reporter.py:75` (returns HMRCHITLProposal, P1 integration deferred) |

---

## Pending BT Blockers (External Action Required)

| BT | Description | Blocking Component | Status | Owner | GAP | Target |
|----|-------------|-------------------|--------|-------|-----|--------|
| BT-001/004 | Provider registry — Twilio OTP + SendGrid + Sumsub + Modulr SEPA live credentials | L3 stubs in `services/auth/production/`, `services/compliance/production/`, `services/payment/production/` | Awaiting CTIO provisioning | CTIO | — | Wave C–D (2026-Q3) |
| BT-003 | SWIFT live fee schedule (correspondent banking) | `services/swift_correspondent/charges_calculator.py:133` | Stub returns estimate; real schedule pending SWIFT SLA | CTIO | — | Wave B P2 (2026-Q2) |
| BT-009 | ML pipeline (fraud scoring) | `services/fraud_tracer/tracer_engine.py` line 112 (returns neutral 0.0) | ML model training in progress (P1) | CTIO | — | 2026-Q3 |
| BT-010 | FCA RegData API key + FCA_FRN + API spec | `services/reporting/regdata_return.py:175–188` (RegDataNotConfiguredError, fail-closed) | Awaiting FCA credentials + FRN provisioning | CEO/CFO | GAP-088 | Blocking FIN060 live submission (P0 deadline 2026-05-07 missed; June 15 projected) |
| BT-014 | Sardine HTTP client credentials (fraud adapter) | `services/fraud/sardine_adapter.py:64` (HTTP call stub) | Awaiting API keys + endpoint spec | CTIO | — | Wave B P2 (2026-Q2) |
| BT-015 | Safeguarding-engine integrations (bank_api, compliance, notification, midaz clients) | `services/safeguarding-engine/app/integrations/{bank_api_client,compliance_client,midaz_client,notification_client}.py` | Returns stubs (P1 integration) | CTIO | — | Phase 3.6 P1 (2026-Q3) |

---

## Cross-References to GAP-REGISTER.md

The following GAP entries reference this L3 Boundary Register:

- **GAP-088** (FCA RegData API key pending — BT-010 blocker): `services/reporting/regdata_return.py:175–188` documents `RegDataNotConfiguredError` fail-closed pattern. Code-complete via `feat/gap088-regdata-fail-closed` with explicit typed exception (no NotImplementedError, but same production seam pattern).  
  → See: [docs/L3-BOUNDARY-REGISTER.md#pending-bt-blockers](docs/L3-BOUNDARY-REGISTER.md#pending-bt-blockers) (BT-010 entry)

- **GAP-089** (Crypto-ledger Wave E Midaz adapter wiring): All 5 NotImplementedError entries in `services/ledger/production/midaz_crypto_stub.py` (lines 44, 55, 65, 76, 83) + 4 delegation hints in legacy adapters (REWRITE-7/8 scope boundaries).  
  → See: [docs/L3-BOUNDARY-REGISTER.md#boundary-registry](docs/L3-BOUNDARY-REGISTER.md#boundary-registry) (entries 1–9)

---

## Audit Trail

**Factory Checklist:**
- [x] All `grep -rn "raise NotImplementedError"` entries classified (22 total)
- [x] BT markers cross-referenced (BT-001 through BT-015 tracked)
- [x] Resolved BTs documented (BT-002/004/005/006/012)
- [x] Pending BTs documented (BT-001/003/004/009/010/014/015)
- [x] GAP-REGISTER cross-references added (GAP-088, GAP-089)
- [x] ADR citations (ADR-117, ADR-025, ADR-031)
- [x] Ruff clean (docs-only, no code changes)

**Status:** READY FOR MERGE (operator HITL gate required per git workflow)

---

**Document Version:** 1.0.0  
**Last Reviewed:** 2026-06-27  
**Next Review:** Post-Wave C / Pre-Wave D (2026-Q3)
