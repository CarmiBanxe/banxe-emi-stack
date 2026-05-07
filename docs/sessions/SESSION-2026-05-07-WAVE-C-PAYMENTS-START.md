# SESSION-2026-05-07-WAVE-C-PAYMENTS-START
# Wave C — PAYMENTS import start: staging + entry-point classification + adapter seam
# Branch: sprint5/wave-c-payments-import-2026-05-07
# Date: 2026-05-07

## 1. Stack Confirmation

Source RAR extracted to evo1:/tmp/banxe-rar-stage/wave-c/ (515 files, 3.0M).

| Metric | Value |
|--------|-------|
| TypeScript (.ts) | 514 files |
| Handlebars (.hbs) | 1 file |
| Python | 0 files |
| Go | 0 files |

**Verdict: 100% NestJS TypeScript.** No Go, no Python. All transport layers (gRPC, Apollo, XML/GCP Bifrost) DROP per ADR-025 §15-16.

Repos in scope:
- **sepa-service** — SEPA/FPS payment orchestration, Papaya loro account integration
- **banxe-transactions** — transaction record parsing, cash/crypto/FX domains
- **banxe-fiat-backend/abs-api** — ABS domain model, GCP Bifrost XML gateway (transport DROP)
- **banxe-manual-payments** — EXCLUDED (React SPA frontend)
- **tompayment-web** — EXCLUDED (React SPA, 2385 components)

---

## 2. Top-15 Entry Points (scored by keyword density)

Keywords: submit | payment | transfer | sepa | fps | chaps | bacs | initiat | execute | process | dispatch

| Rank | Score | Path | Verdict | Port Target |
|------|-------|------|---------|-------------|
| 1 | 159 | banxe-fiat-backend/abs-api/src/abs/services/abs-customer.service.ts | EXCLUDE | customer onboarding |
| 2 | 104 | banxe-fiat-backend/abs-api/src/abs/services/abs-user.service.ts | EXCLUDE | user management |
| 3 | 74 | banxe-fiat-backend/abs-api/src/abs/services/abs-customer-contract.service.ts | EXCLUDE | contract lifecycle |
| 4 | 62 | banxe-fiat-backend/abs-api/src/abs/services/abs-legal-entity.service.ts | EXCLUDE | KYC/entity |
| 5 | 48 | banxe-transactions/src/transactions/services/cash/payment-transaction.service.ts | **REWRITE-1** | `get_payment_status()` + audit |
| 6 | 42 | banxe-transactions/src/transactions/services/crypto/crypto-processing-transaction.service.ts | SKIP-wave-c | crypto out of scope |
| 7 | 37 | banxe-fiat-backend/abs-api/src/abs/services/abs-customer-payment.service.ts | **REWRITE-2** | `submit_payment()` ABS domain |
| 8 | 32 | sepa-service/src/transactions/create-outgoing-transactions.service.ts | **REWRITE-3** | `submit_payment()` SEPA CT/INSTANT |
| 9 | 31 | banxe-fiat-backend/abs-api/src/abs/services/abs-agreement.service.ts | EXCLUDE | agreement lifecycle |
| 10 | 26 | banxe-fiat-backend/abs-api/src/abs-api/services/abs-api-customer-payment.service.ts | REWRITE-4 | `submit_payment()` GCP Bifrost XML |
| 11 | 22 | banxe-fiat-backend/abs-api/src/abs/services/abs-cron-process.service.ts | SKIP-wave-c | cron — infrastructure |
| 12 | 19 | sepa-service/src/sepa-accounts/listeners/sync-account-status.listener.service.ts | SKIP-wave-c | account status sync |
| 13 | 18 | banxe-transactions/src/transactions/services/cash-transaction.service.ts | REWRITE-5 | `get_payment_status()` enrichment |
| 14 | 16 | sepa-service/src/sepa-accounts/listeners/sepa-account-confirm.listener.service.ts | SKIP-wave-c | account confirm listener |
| 15 | 16 | sepa-service/src/sepa-accounts/get-sepa-accounts.service.ts | SKIP-wave-c | account query |

---

## 3. Top-3 REWRITE Candidates — Semantic Mapping to PaymentRailPort

### REWRITE-1: payment-transaction.service.ts → LegacyTransactionsAdapter

**Port target:** `PaymentRailPort.get_payment_status(provider_payment_id: str) → PaymentResult`

**TS method mapping:**
| TS method | Python equivalent |
|-----------|------------------|
| `parse(transaction, sendFromService, ...)` | Status enrichment inside `get_payment_status()` |
| `resolveBasePayment()` — maps tx fields to domain | `PaymentResult` field population |
| `resolveBaseBalances()` — pre/post-COMPLETED balances | Audit trail emission (not in port return) |

**What DROPS:** TypeORM entity `CashTransactionEntity`, NestJS DI decorators, Redis cache read-through.

**What MAPS:** Transaction status logic → `PaymentStatus` enum (PENDING/PROCESSING/COMPLETED/FAILED/RETURNED/CANCELLED), idempotency_key passthrough, amount as `Decimal` (I-01), currency validation.

**Risk:** `resolveBaseBalances()` touches balance accounting — needs careful mapping to avoid double-counting. Separate concern from port; emit via `AuditPort`, not `PaymentResult`.

---

### REWRITE-2: abs-customer-payment.service.ts → LegacyAbsPaymentAdapter

**Port target:** `PaymentRailPort.submit_payment(intent: PaymentIntent) → PaymentResult`

**TS method mapping:**
| TS method | Python equivalent |
|-----------|------------------|
| `createOrUpdateCustomerPayment(dto)` | `submit_payment(intent)` → stores in-memory |
| `approveCustomerPayment(id, vop)` | Part of `submit_payment()` confirm phase |
| Bank ref / doc number generation | Internal `_generate_ref()` helper |

**What DROPS:** XML map templates, GCP Bifrost transport (`requestToGCPProcessing`), sequential counters via DB.

**What MAPS:** Payment amount as `Decimal`, debtor/creditor account → `BankAccount`, `PaymentRail.SEPA_CT` default, status → `PaymentStatus.PENDING` on create.

**Risk:** Sequential doc number counter (TypeORM) → replace with `secrets.token_hex(8)` prefix + timestamp; atomic counter not needed in dev/test; Redis counter in Wave D.

---

### REWRITE-3: create-outgoing-transactions.service.ts → LegacySepaAdapter

**Port target:** `PaymentRailPort.submit_payment(intent: PaymentIntent) → PaymentResult`

**TS method mapping:**
| TS method | Python equivalent |
|-----------|------------------|
| `approveTransaction(dto)` — SEPA outbound | `submit_payment(intent)` |
| `needsApprovalHandler()` — cron 30min | DROP (in-memory adapter handles synchronously) |
| Papaya loro account lookup | `intent.debtor_account` (caller provides) |
| DWH payment service call | DROP (separate DwhPort, Wave D) |

**What DROPS:** Redis cron/lock, DWH microservice gRPC, NestJS EventEmitter, TypeORM repository.

**What MAPS:** SEPA transaction direction → `PaymentIntent.direction = "outbound"`, rail → `PaymentRail.SEPA_CT` or `SEPA_INSTANT`, VOP approving party → `intent.reference`, end_to_end_id passthrough.

**Risk:** Papaya loro account is hardcoded in TS. In Python, inject via constructor param or config env var — never hardcode (security policy).

---

## 4. Adapter Seam Plan

**Location:** `services/payment/legacy/`

Rationale: The existing `PaymentRailPort` lives at `services/payment/payment_rail_port.py`. Legacy adapters follow the same `services/<domain>/legacy/` pattern established in Wave A (auth) and Wave B (auth/sca).

**Planned adapters (Wave C Step 1+):**
```
services/payment/legacy/
├── __init__.py                          ← anchor (this PR)
├── legacy_sepa_adapter.py               ← REWRITE-3 (Wave C Step 1)
├── legacy_transactions_adapter.py       ← REWRITE-1 (Wave C Step 2)
└── legacy_abs_payment_adapter.py        ← REWRITE-2 (Wave C Step 3)
```

**Port conformance:** each adapter implements `PaymentRailPort` (structural, same as ScaServicePort pattern — not `@runtime_checkable`).

**In-memory backend:** dict keyed by `idempotency_key`, durable Redis adapter deferred to Wave D.

---

## 5. Frozen Invariants for Wave C Adapters

- `amount: Decimal` always — never `float` (I-01)
- `idempotency_key` required in `PaymentIntent` — duplicate check before store
- All payment events logged (audit trail) — I-24 append-only
- No hardcoded credentials or Papaya account numbers — environment config (security-policy.md)
- Blocked jurisdictions checked before `submit_payment()` — I-02 (RU/BY/IR/KP/CU/MM/AF/VE/SY)
- `PaymentRail` enum: FPS / SEPA_CT / SEPA_INSTANT / BACS / CHAPS — no free-string rails

---

## 6. Canon

- ADR-025 §15-16 (REWRITE-1 adapter constraints — DROP transport, map semantics)
- `services/payment/payment_rail_port.py` (PaymentRailPort Protocol)
- `docs/inventories/WAVE-C-PAYMENTS-PATHS.txt` (filtered source paths)
- `docs/inventories/WAVE-C-PAYMENTS-ENTRY-POINTS-2026-05-07.txt` (scored entry points)
- AUTH_IMPORT_ORDER pattern (import discipline — ports don't import from legacy/)
- Wave A canon: `services/auth/legacy/` (JWT + RoleGuard adapters, PR #75)
- Wave B canon: `services/auth/legacy/` (TOTP adapter PR #77, SCA adapter PR #79)
