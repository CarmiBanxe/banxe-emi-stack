# SESSION-2026-05-09 — Sprint 6 Start Canon

**Date:** 2026-05-09  
**Phase:** Sprint 6 — Production AUTH integrations (OTP Delivery Port)  
**Branch (source PR):** docs/sprint-6-start-canon-2026-05-09 (squashed manually via PR #93)

---

## Phase 5 Status

- PR #92 merged: Phase 5 consolidation CLOSED (Tranche 5 — release notes + production wiring stubs).
- 9 hexagonal ports FROZEN (see docs/phase5/PORT-CONTRACTS-FREEZE-2026-05-08.md).
- api/routers/auth.py remains transport-only; no changes in Phase 5.
- 5 production stubs created in /production/ subdirs (Twilio, SendGrid, Modulr, Midaz, SumSub).

---

## Sprint 6–12 Roadmap (Binding)

### Sprint 6 — Production AUTH integrations (ACTIVE)

Goal:
- Replace TwilioOtpStub and SendGridOtpStub with real adapters behind OtpDeliveryPort (FROZEN).

Adapters:
- services/auth/production/twilio_otp_adapter.py
- services/auth/production/sendgrid_otp_adapter.py

Environment:
- TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
- SENDGRID_API_KEY, SENDGRID_FROM_EMAIL

Acceptance criteria:
- Twilio adapter calls Verify API (sandbox) with correct from/locale/rate-limit behaviour.
- SendGrid adapter uses Mail Send API with sandbox mode enabled by default in tests.
- No changes to OtpDeliveryPort interface or semantics.
- Integration tests against Twilio/SendGrid sandboxes.
- Coverage ≥ 80% on new production adapters.

### Sprint 7 — Production COMPLIANCE (SumSub)

Goal:
- Replace SumsubHttpStub with real SumSub REST adapter + webhook handler.

Acceptance criteria:
- Applicant create/status endpoints wired via KYCWorkflowPort.
- Webhook signature verification via HMAC-SHA256 and SUMSUB_WEBHOOK_SECRET.
- I-02, I-04, I-24, I-27 enforced end-to-end.
- Integration tests vs SumSub sandbox.
- Coverage ≥ 80%.

### Sprint 8 — Production PAYMENTS (Modulr SEPA)

Goal:
- Replace ModulrSepaStub with real Modulr Payment Initiation adapter.

Acceptance criteria:
- SEPA CT initiation via Modulr sandbox endpoint.
- Idempotency keys on all payment requests.
- Webhook signature verification.
- Integration tests vs Modulr sandbox.
- Coverage ≥ 80%.

### Sprint 9 — Production CRYPTO/LEDGER (Midaz)

Goal:
- Replace MidazCryptoStub with real Midaz Ledger API adapter.

Acceptance criteria:
- Real account/transaction calls to Midaz.
- Atomic transaction semantics enforced at adapter level.
- Integration tests vs Midaz sandbox / local docker.
- Coverage ≥ 80%.

### Sprint 10 — BANXE.RAR Remaining Inventory

Goal:
- Classify remaining BANXE.RAR directories (PASS/REWRITE/REJECT) and open inventory PRs.

Candidates:
- banxe/banxe-shared-libs
- banxe/banxe-trade-view-new
- internal_dev/support-services
- internal_dev/trigger-system-services
- internal_dev/finthech-services
- banxe-digital/v-accounting
- banxe-digital/crypto-exchange-api
- banxe-uikit (likely DROP)
- consul-configs (DROP)
- neuron/* (separate ecosystem, assess relevance)

Acceptance criteria:
- Inventory PR per candidate with classification.
- Follow-up adapter PRs for PASS items.

### Sprint 11 — AI-Agent Training Data

Goal:
- Extract domain knowledge from BANXE.RAR into docs/training/ for AI agents.

Output:
- Structured documents: use-cases, business rules, error taxonomies.
- No legacy code copies, only domain semantics.

ADR:
- ADR-035 (training data extraction methodology, Proposed → Accepted in this sprint).

### Sprint 12 — End-to-End Production Verification

Goal:
- Full sandbox journey: registration → KYC → 2FA → SEPA payment → crypto transaction.

Acceptance criteria:
- All steps executed through production adapters (Twilio, SendGrid, SumSub, Modulr, Midaz).
- Smoke tests green in CI (sandbox only).
- ADR-036 (roadmap completion) accepted with final release notes.

---

## Sandbox-Priority Canon (Binding)

- All external integrations use sandbox/test credentials in CI and default configs.
- No real OTP/SMS/email, no real KYC applicants, no live money movements from test runs.
- Production endpoints may be configured only in operator-controlled environments, never in CI.

---

## AI-Agent Training Canon (Binding)

- BANXE.RAR is treated as domain-knowledge corpus, not as code to be cloned.
- Extracted material lives under docs/training/, structured for prompts/agents.
- Any training dataset derived from BANXE.RAR must exclude secrets and personally identifiable data.

---

## Frozen Contracts (No Changes Without ADR)

- 9 hexagonal ports (see PORT-CONTRACTS-FREEZE-2026-05-08.md).
- api/routers/auth.py (transport-only).
- services/_legacy_common/*
- services/auth/legacy/*, services/payment/legacy/*, services/compliance/legacy/*, services/ledger/legacy/*.
- decisions/ADR-001..ADR-030.

---

## Execution Canon References

- ADR-025 — Agent Interaction Canon (OCAT, whitelists, non-safe ops, best-decision principle).
- ADR-026 — Guardian agent bash family (bash shim + factory/project scopes).
- ADR-029 — OTP Delivery Port (contract, invariants, allowed adapter behaviours).

---

## Default Merge Pattern (Docs + Code)

1. Branch from main → push to origin.
2. gh pr create (no draft).
3. gh pr checks <N> --watch --interval 15 (CI green).
4. gh pr merge <N> --squash --delete-branch --admin (if branch protection requires).
5. git checkout main && git pull.
