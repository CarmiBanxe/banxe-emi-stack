# SESSION-2026-05-07 — Wave B SCA/2FA Import Start
# Phase 4 | Branch: sprint5/wave-b-sca-2fa-import-2026-05-07
# Canon: ADR-015 + ADR-025 §15-16 + AUTH_MATRIX + AUTH_IMPORT_ORDER
# P0 Deadline: 7 May 2026

## 1. Staging Summary

| Item | Value |
|------|-------|
| Staging path | evo1:/tmp/banxe-rar-stage/wave-b (read-only) |
| Files extracted | 984 |
| Disk size | 5.1 MB |
| NOT in repo | Confirmed (classification docs only) |
| Source RAR | /backup/banxe.rar |

## 2. Stack Confirmed

| Repo | Language | Framework | Role |
|------|----------|-----------|------|
| banxe-auth | TypeScript | NestJS 8 + TypeORM | OTP code service + SCA challenge |
| banxe-common | TypeScript | NestJS + gRPC | 2FA gRPC connector to banxe-2fa microservice |
| banxe-dashboard | TypeScript | React 18 + Apollo | 2FA UI (frontend reference only) |
| sumsub-test | JavaScript | Node.js (plain) | KYC identity verification test harness |
| banxe-crypto-earn | TypeScript | NestJS | send-2fa DTO (peripheral) |

**2FA types in upstream:** `SMS`, `EMAIL`, `OTP` (TOTP) — enum `TFATypeEnum` in banxe-common

## 3. Top-15 Entry Points

| Rank | Score | File | Verdict | Rationale |
|------|-------|------|---------|-----------|
| 1 | 18 | banxe-dashboard/TwoFA/model/confirmNewIdentity.ts | **REJECT** | React state model; no backend logic |
| 2 | 15 | banxe-dashboard/TwoFA/model/confirmTwoFAModal.ts | **REJECT** | React Effector model; frontend only |
| 3 | 15 | banxe-common/2fa-connector/queries/index.ts | **PASS** | gRPC query type re-export; no logic |
| 4 | 14 | banxe-dashboard/TwoFA/ui/ConfirmTwoFAModal/index.tsx | **REJECT** | React UI component; no EMI port |
| 5 | 11 | banxe-dashboard/TwoFA/ui/TwoFAInput/index.tsx | **REJECT** | React input component; no EMI port |
| 6 | 9 | banxe-common/2fa-connector/2fa-connector.service.ts | **REWRITE** | gRPC TOTP/2FA transport → TwoFactorPort |
| 7 | 8 | banxe-auth/src/auth/auth.service.ts | **REWRITE** | SCA ECDH challenge + JWT → ScaServicePort |
| 8 | 7 | banxe-common/lib/graphql/scalars/index.ts | **PASS** | Scalar re-export; no 2FA logic |
| 9 | 6 | banxe-dashboard/TwoFA/types.ts | **REJECT** | TypeScript type defs; frontend only |
| 10 | 6 | banxe-auth/src/code/code.service.ts | **REWRITE** | OTP send/verify service → TwoFactorPort |
| 11 | 6 | banxe-auth/src/code/code.resolver.ts | **REVIEW** | Thin GraphQL resolver; logic in service |
| 12 | 5 | banxe-dashboard/TwoFA/ui/ConfirmNewIdentityModal/index.tsx | **REJECT** | React UI; no EMI port |
| 13 | 5 | banxe-common/identity-connector.service.ts | **REVIEW** | Identity SCA-adjacent; not core 2FA |
| 14 | 5 | banxe-auth/src/auth/auth.resolver.ts | **REVIEW** | Thin GraphQL resolver; logic in service |
| 15 | 4 | banxe-common/2fa-connector/queries/verify-2fa-token.query.ts | **PASS** | Single gRPC query definition; no logic |

**Summary:** 3 REWRITE, 4 REVIEW, 3 PASS, 5 REJECT (frontend/UI)

## 4. Top-3 REWRITE Candidates

### REWRITE-1: banxe-auth/src/code/code.service.ts
**Language:** TypeScript/NestJS | **Lines:** 206 | **EMI Port:** `TwoFactorPort`

**What it does:**
- Generates random 5-char OTP codes, persists to PostgreSQL via TypeORM
- Sends via Apollo GraphQL to notification microservice (registerDevice → send mutations)
- Verifies submitted code against stored record

**Issues requiring rewrite (not patch):**
- `require('mongoose').Types.ObjectId` mixed into PostgreSQL service (dead code, wrong DB)
- Apollo client constructed inline (`new ApolloClient(...)`) — not DI-injectable
- `uuid: 'uuid'` hardcoded string in registerDevice mutation (known upstream bug)
- No code TTL/expiry enforcement (`retryDelay: code.dateCreated // discuss with Roman`)
- No rate limiting (brute-force OTP trivially easy)
- Raw `process.env.NOTIFICATION_API_GRAPHQL_URL` — not via config service

**Semantic mapping to EMI:**
```
code.service.ts::sendCode()    → TwoFactorPort.send_otp(customer_id, destination, method)
code.service.ts::checkCode()   → TwoFactorPort.verify_otp(code_id, customer_id, otp)
CodeType.EMAIL / .SMS          → TwoFactorMethod.EMAIL / .SMS
CodeEntity (TypeORM)           → persisted in Keycloak OTP store (no EMI DB write needed)
```

**Target:** `services/auth/legacy/legacy_otp_adapter.py`

---

### REWRITE-2: banxe-auth/src/auth/auth.service.ts
**Language:** TypeScript/NestJS | **Lines:** 345 | **EMI Port:** `ScaServicePort`

**What it does:**
- `challenge()` — ECDH P-256 key exchange: generate server nonce, sign with SERVER_PRIVATE_KEY
- `init()` / `authorization()` — JWT issue (access + refresh) after credential check
- Device management (add-device, add-my-device)
- Phone/email uniqueness check

**Issues requiring rewrite:**
- `require('mongoose')` — legacy MongoDB ORM dependency in NestJS TypeScript service
- `Buffer.from(process.env.SERVER_PRIVATE_KEY)` — raw env, no validation/rotation
- Apollo client inlined (notification calls not via injected port)
- ECDH challenge flow not PSD2-compliant for EMI (needs transaction binding per SCA)
- No challenge TTL, no replay protection

**Semantic mapping to EMI:**
```
auth.service.ts::challenge()   → ScaServicePort.create_challenge(customer_id, txn_id, method="OTP")
challenge.type.ts::Challenge   → SCAChallenge (sca_models.py)
challenge expiry               → SCA_CHALLENGE_TTL_SEC (already in sca_service.py)
JWT issue after auth           → existing token_manager.py (already wired)
```

**Target:** `services/auth/legacy/legacy_sca_adapter.py`

---

### REWRITE-3: banxe-common/lib/.../2fa-connector.service.ts
**Language:** TypeScript/NestJS | **Lines:** 314 | **EMI Port:** `TwoFactorPort`

**What it does:**
- gRPC transport layer to `banxe-2fa` external microservice
- Methods: generateTOTP, create/get 2FAOperationId, getEnabled2FA, send2FAToken, verify2FAToken, enable2FA, disable2FA, confirmEnable/Disable, generateOneTimeCode, confirmOneTimeCode, checkResendOneTimeCode

**Issues requiring rewrite:**
- gRPC transport (`BaseConnectorGrpcService`) not available in EMI Python stack
- Depends on running `banxe-2fa` microservice (not part of P0 stack)
- No Python equivalent; TOTP logic must move to `pyotp` (self-hosted, no external service)
- `TFA_SERVICE_NAME_ENV = '2FA'` — env-based service discovery not portable

**Semantic mapping to EMI:**
```
generateTOTP()         → TwoFactorPort.setup_totp(customer_id)          [pyotp.TOTP]
verify2FAToken()       → TwoFactorPort.verify_totp(customer_id, otp)
enable2FA() / disable  → TwoFactorPort.confirm_totp() / revoke_totp()
generateOneTimeCode()  → TwoFactorPort.send_otp() (OTP via Keycloak SMS/EMAIL)
getRecoveryCode()      → TwoFactorPort.verify_backup_code()
TFATypeEnum: SMS/EMAIL/OTP → TwoFactorMethod enum (two_factor.py)
```

**Target:** `services/auth/legacy/legacy_totp_adapter.py`

## 5. Adapter Seam Plan

```
services/auth/legacy/
├── __init__.py               (existing)
├── jwks_models.py            ✅ Wave A — RFC-7517 JWKS models
├── jwt_strategy.py           ✅ Wave A — RS256 JWT validation
├── role_guard.py             ✅ Wave A — require_roles FastAPI dep
├── legacy_otp_adapter.py     🔜 Wave B — implements TwoFactorPort (OTP send/verify)
├── legacy_totp_adapter.py    🔜 Wave B — implements TwoFactorPort (TOTP via pyotp)
└── legacy_sca_adapter.py     🔜 Wave B — implements ScaServicePort (challenge lifecycle)
```

**Ports already defined (no changes needed):**
- `TwoFactorPort` — `services/auth/two_factor_port.py`
- `ScaServicePort` — `services/auth/sca_service_port.py`
- `SCAChallenge`, `SCAVerifyResult` — `services/auth/sca_models.py`
- `TOTPSetup`, `VerifyResult` — `services/auth/two_factor.py`

**Test targets (per .claude/CLAUDE.md §30-testing ≥15 tests/component):**
- `tests/test_legacy_otp_adapter.py` — ≥20 tests (send, verify, rate limit, TTL, method enum)
- `tests/test_legacy_totp_adapter.py` — ≥20 tests (setup, confirm, verify, backup, revoke)
- `tests/test_legacy_sca_adapter.py` — ≥20 tests (create, verify, resend, TTL, replay-protection)

## 6. What NOT in Wave B

- `banxe-dashboard/TwoFA/**` — React UI; excluded (frontend wave, not P0 auth)
- `banxe-crypto-earn/src/earn/dtos/send-2fa.dto.ts` — peripheral DTO; Wave C
- `sumsub-test/**` — KYC harness; Wave C (KYC import)
- Any gRPC infrastructure — EMI stack uses HTTP; no gRPC in P0

## 7. Next Step

Wave B wiring sprint: implement the 3 REWRITE adapters behind existing ports.
No new ports. No router changes. No schema changes.
