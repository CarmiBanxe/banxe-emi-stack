# BANXE.RAR → EMI Smart Refactor — Phase 4+5 Release Notes (2026-05-08)

**Branch Canon:** PR #60 (roadmap origin)  
**Scope:** 5 migration waves (Wave A–E) + 5 Phase 5 consolidation tranches  
**Inventory:** 100,488 source files classified (PR #106, banxe-architecture)  
**Deadline:** FCA CASS 15 / PS25/12 — 7 May 2026 ✅ delivered on time

---

## Summary

BANXE.RAR → EMI Smart Refactor replaces the legacy TypeScript NestJS microservice mesh
with a Python hexagonal architecture behind frozen port contracts. Transport layers
(gRPC, TypeORM, RabbitMQ, NestJS DI/EventEmitter, GCP Bifrost XML) are dropped per
ADR-025 §15-16 and replaced with in-memory adapters for dev/test and production stubs
for the future production team.

---

## Wave A — AUTH/IAM

**Status:** ✅ 100% closed  
**Files:** `services/auth/legacy/jwt_strategy.py`, `jwks_models.py`, `role_guard.py`  
**Ports:** `TokenManagerPort`, `IAMPort` — FROZEN  
**Tests:** 65  
**Canon:** ADR-015 + AUTH_MATRIX

### What was delivered
- `LegacyJwtStrategyAdapter` — JWT validation behind `TokenManagerPort`; drops Passport.js
- `LegacyRoleGuardAdapter` — RBAC enforcement behind `IAMPort`; drops NestJS `@Roles()`
- `JWKSModels` — frozen Pydantic v2 models for JWKS endpoint response
- `api/routers/auth.py` — transport-only, untouched throughout all waves

### What was dropped
- Passport.js / NestJS JWT guard
- GrpcCompaniesConnector for role resolution
- ConfigService (`JWT_SECRET`, `JWKS_URL`) global singletons

---

## Wave B — SCA/2FA

**Status:** ✅ 100% closed  
**Files:** `legacy_totp_adapter.py`, `legacy_otp_adapter.py`, `legacy_sca_adapter.py`  
**Ports:** `TwoFactorPort`, `OtpDeliveryPort`, `ScaServicePort` — FROZEN  
**Tests:** ~93  
**Canon:** ADR-015 + ADR-029

### What was delivered
- `LegacyTotpAdapter` — TOTP lifecycle (setup/confirm/verify/backup codes) behind `TwoFactorPort`
- `LegacyOtpAdapter` — OTP generation/delivery/verification (in-memory, NIST SP 800-63B); drops gRPC notification
- `LegacyScaAdapter` — SCA challenge orchestration behind `ScaServicePort`
- `OtpDeliveryPort` — Protocol contract for SMS/email OTP (ADR-029, now FROZEN)
- Security: `hmac.compare_digest` constant-time comparison; `secrets.choice` NIST-compliant

### What was dropped
- CodeService gRPC notification transport
- NestJS EventEmitter OTP delivery
- Redis cron for OTP expiry (replaced by in-memory TTL)

---

## Wave C — PAYMENTS

**Status:** ✅ 100% closed  
**Files:** `legacy_transactions_adapter.py`, `legacy_abs_payment_adapter.py`, `legacy_sepa_adapter.py`  
**Port:** `PaymentRailPort` — FROZEN  
**Tests:** ~159  
**Canon:** ADR-025 §15-16 + I-01/I-02/I-24

### What was delivered
- `LegacyTransactionsAdapter` — internal transaction lifecycle; drops TypeORM `TransactionEntity`
- `LegacyAbsPaymentAdapter` — ABS payment rail (submit/status/cancel); drops GCP Bifrost XML
- `LegacySepaAdapter` — SEPA CT + SCT Inst; drops Modulr direct HTTP; composite idempotency key; 2dp precision enforcement

### What was dropped
- GCP Bifrost XML dispatch
- TypeORM repositories (`TransactionEntity`, `PaymentEntity`)
- RabbitMQ publishers for payment events
- NestJS DI / `@InjectRepository`

---

## Wave D — KYC/COMPLIANCE

**Status:** ✅ 99% closed (SumSub webhook handler deferred to Wave E-II)  
**Files:** `legacy_sumsub_adapter.py`, `legacy_bkyc_adapter.py`, `legacy_binancekyc_adapter.py`  
**Port:** `KYCWorkflowPort` — FROZEN  
**Tests:** ~155  
**Canon:** ADR-025 §15-16 + I-02/I-04/I-24/I-27

### What was delivered
- `LegacySumSubAdapter` — KYC workflow (PENDING→DOCUMENT_REVIEW→RISK_ASSESSMENT→EDD→MLRO→APPROVED/REJECTED); I-02 jurisdiction block; I-04 EDD thresholds
- `LegacyBKYCAdapter` — business KYC supplemental; drops TypeORM `UserIdentityDocEntity`
- `LegacyBinanceKYCAdapter` — tiered KYC (BASIC/ENHANCED); MLRO sign-off gate (I-27)
- `_jurisdictions.py` — shared I-02 block list (RU/BY/IR/KP/CU/MM/AF/VE/SY)
- `_edd.py` — shared I-04 EDD threshold check (£10k individual / £50k corporate)

### What was dropped
- SumSub HMAC-signed axios HTTP client
- TypeORM `SumsubConfigEntity`, `AvailableErc20TokenForSumsubEntity`
- GrpcCompaniesConnector, GrpcAddressesConnector, AbsLegalEntityConnector
- Amplitude analytics calls
- NestJS DI / `@Injectable` / `@InjectRepository`
- RabbitMQ publishers for KYC events

---

## Wave E — CRYPTO/LEDGER

**Status:** ✅ 100% closed  
**Files:** `legacy_crypto_ledger_adapter.py`, `legacy_crypto_processing_adapter.py`, `legacy_crypto_rpc_adapter.py`  
**Ports:** `CryptoLedgerPort`, `CryptoRpcPort` — FROZEN  
**Tests:** 142  
**Canon:** ADR-031 + ADR-025 §15-16 + I-01/I-24

### What was delivered
- `LegacyCryptoLedgerAdapter` (REWRITE-7) — wallet balance + address derivation; drops web3/ethers direct
- `LegacyCryptoProcessingAdapter` (REWRITE-8) — crypto transaction lifecycle; drops bitcoinjs-lib
- `LegacyCryptoRpcAdapter` (REWRITE-9) — blockchain RPC abstraction; drops TronWeb/EthersJS direct HTTP
- `CryptoApplicationService` — orchestration layer wiring CryptoLedgerPort + CryptoRpcPort
- `/v1/crypto-legacy` router — transport layer (untouched after wire-up)

### What was dropped
- web3.js / ethers.js direct blockchain calls
- bitcoinjs-lib direct UTXO management
- TronWeb direct gRPC/HTTP calls
- NestJS DI / `@InjectRepository` for crypto entities

---

## Phase 5 Consolidation

### Tranche 1 — Crypto DI Wiring + Shared Error Hierarchy (PR #89)
- `CryptoApplicationService` injected into production DI
- `/v1/crypto-legacy` router wired
- Payment adapter health normalization (all adapters return `bool`)
- `BanxeLegacyAdapterError` — shared base exception for all legacy adapters

### Tranche 2 — Port Contracts Freeze + Shared Modules (PR #90)
- `docs/phase5/PORT-CONTRACTS-FREEZE-2026-05-08.md` — all 9 ports formally FROZEN
- `services/compliance/legacy/_jurisdictions.py` — extracted from SumSub/BinanceKYC (I-02, 9 blocked codes)
- `services/compliance/legacy/_edd.py` — extracted from SumSub (I-04, £10k/£50k thresholds)

### Tranche 3+4 — Shared Audit Base + OTPDeliveryPort Frozen (PR #91)
- `services/_legacy_common/audit.py` — `BaseAuditRecord` (frozen Pydantic, I-24) + `AuditTrail` (copy-on-read)
- `services/_legacy_common/state_machine.py` — `assert_valid_transition` + `is_terminal`
- All 5 legacy adapter `*AuditRecord` classes refactored to inherit `BaseAuditRecord`
- `OtpDeliveryPort` promoted from ACTIVE → FROZEN; full method signatures recorded
- 29 new tests in `tests/_legacy_common/`

### Tranche 5 — Release Notes + Production Wiring Stubs (this PR)
- This document
- 4 production stub modules: `TwilioOtpStub`, `SendGridOtpStub`, `ModulrSepaStub`, `MidazCryptoStub`, `SumsubHttpStub`
- `tests/test_production_stubs.py` — Protocol conformance + `NotImplementedError` sanity (11 tests)

---

## Architecture Invariants Enforced

| Invariant | Rule | Adapters |
|-----------|------|---------|
| I-01 | `Decimal` only for monetary amounts — never `float` | All payment + crypto adapters |
| I-02 | Jurisdiction block: RU/BY/IR/KP/CU/MM/AF/VE/SY | SumSub, BinanceKYC, SEPA |
| I-04 | EDD threshold: £10k individual / £50k corporate | SumSub, BinanceKYC |
| I-24 | Append-only audit trail — `BaseAuditRecord` frozen, never updated | All 5 adapters |
| I-27 | HITL — MLRO sign-off required for EDD approval | SumSub, BinanceKYC |

## Frozen Port Contracts

| Port | Location | Waves |
|------|----------|-------|
| `TokenManagerPort` | `services/auth/token_manager_port.py` | Wave A |
| `IAMPort` | `services/auth/` | Wave A |
| `TwoFactorPort` | `services/auth/two_factor_port.py` | Wave B |
| `ScaServicePort` | `services/auth/sca_service_port.py` | Wave B |
| `OtpDeliveryPort` | `services/auth/otp_delivery_port.py` | Wave B |
| `PaymentRailPort` | `services/payment/payment_port.py` | Wave C |
| `KYCWorkflowPort` | `services/kyc/kyc_port.py` | Wave D |
| `CryptoLedgerPort` | `services/ledger/crypto_ledger_port.py` | Wave E |
| `CryptoRpcPort` | `services/ledger/crypto_ledger_port.py` | Wave E |

## Transport Drops (ADR-025 §15-16)

| Transport | Replaced by |
|-----------|-------------|
| gRPC (all services) | In-memory adapters / future REST adapters |
| TypeORM repositories | Frozen Pydantic models + in-memory dicts |
| Redis cron (OTP expiry) | In-memory TTL; Redis adapter planned (Wave C) |
| NestJS DI / EventEmitter | Constructor injection / Protocol DI |
| GCP Bifrost XML | In-memory stub; Modulr stub planned |
| RabbitMQ publishers | No event bus in scope; ClickHouse audit log |
| Amplitude analytics | Removed (not FCA-regulated) |

---

## What Is NOT Done — Production Wiring Required

These adapters are in-memory only. Production integrations must be implemented separately:

| Stub | File | Required env vars | Ticket |
|------|------|-------------------|--------|
| `TwilioOtpStub` | `services/auth/production/twilio_otp_stub.py` | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | IL-OTP-PROD-01 |
| `SendGridOtpStub` | `services/auth/production/twilio_otp_stub.py` | `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`, `SENDGRID_OTP_TEMPLATE_ID` | IL-OTP-PROD-02 |
| `ModulrSepaStub` | `services/payment/production/modulr_sepa_stub.py` | `MODULR_API_KEY`, `MODULR_BASE_URL` | IL-SEPA-PROD-01 |
| `MidazCryptoStub` | `services/ledger/production/midaz_crypto_stub.py` | `MIDAZ_API_KEY`, `MIDAZ_LEDGER_URL` | IL-CRYPTO-PROD-01 |
| `SumsubHttpStub` | `services/compliance/production/sumsub_http_stub.py` | `SUMSUB_APP_TOKEN`, `SUMSUB_SECRET_KEY`, `SUMSUB_BASE_URL` | IL-KYC-PROD-01 |

---

## Canon References

- ADR-015: Auth seam + Wave B boundary
- ADR-025 §15-16: Transport drop policy + legacy adapter protocol
- ADR-029: OtpDeliveryPort contract (Proposed)
- ADR-031: CryptoLedgerPort contract (Proposed)
- AUTH_MATRIX: Role ↔ permission matrix (banxe-architecture)
- AUTH_IMPORT_ORDER: Auth service dependency order (banxe-architecture)
- PORT-CONTRACTS-FREEZE-2026-05-08: All 9 ports formally frozen
