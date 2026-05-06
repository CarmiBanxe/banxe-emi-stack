# Wave A backend — AUTH / IAM re-scope start

**Date:** 2026-05-06
**Branch:** `sprint5/wave-a-backend-auth-iam-2026-05-06` (from `main` @ `b1a8a84`)
**Canon:** ADR-015 (auth ports) + ADR-025 §16 (shell hygiene) + AUTH_MATRIX.md + AUTH_IMPORT_ORDER.md
**Status:** OPEN — staging done, classification with real code review, no legacy files committed.

---

## Re-scope rationale (frontend → backend)

Previous Wave A attempt (PR #71 / `sprint5/wave-a-auth-iam-import-2026-05-06`) staged `banxe/banxe_auth` + `banxe/common_auth_web` and surfaced an architectural-fit gap: both repos turned out to be **frontend TypeScript / React / Apollo** (183 `.ts` + 118 `.tsx` SPA, 179 `.tsx` + 91 `.ts` boilerplate). They cannot attach behind backend ports `TokenManagerPort` / `IAMPort` / `TwoFactorPort`.

This Wave A backend re-scope targets the actual backend AUTH/IAM repos identified in Phase 3 inventory:

| Repo | Listing entries | Verified | Stack |
|---|---:|:-:|---|
| `banxe/auth-service` | 87 | ✅ | NestJS reusable lib `@i-link/auth-service` v0.0.12 |
| `banxe/banxe-tx-auth` | 278 | ✅ | NestJS GraphQL service (Passport JWT + Redis + RabbitMQ) |
| `banxe/banxe-identity-config-manager` | 67 | ✅ | NestJS app (TypeORM config-driven IAM config) |
| **Total** | **432** | | |

Path subset persisted to `docs/inventories/WAVE-A-BACKEND-PATHS.txt`.

---

## Stage location (NOT committed)

| Field | Value |
|---|---|
| Host | `evo1` |
| Path | `/tmp/banxe-rar-stage/wave-a-backend` |
| Source | `/backup/banxe.rar` (SHA-256 `420913292bf38c50543cbcecd8c2079e050f8d3fc588b1f7f145605af0e1bf13`) |
| Extracted | `banxe/auth-service/*`, `banxe/banxe-tx-auth/*`, `banxe/banxe-identity-config-manager/*` |
| Staging size | **6.8 MB** |
| Files extracted (incl. `.git/`) | **311 regular files** |
| Local-first rule | RAR + extracted files remain on evo1; no cloud upload, no broader movement (canon ADR-025 §3.2) |
| Repo artefacts | `docs/inventories/WAVE-A-BACKEND-PATHS.txt`, `docs/inventories/WAVE-A-BACKEND-ENTRY-POINTS-2026-05-06.txt` only |

Reproduce extraction:
```
ssh banxe@evo1 'rm -rf /tmp/banxe-rar-stage/wave-a-backend; mkdir -p /tmp/banxe-rar-stage/wave-a-backend; cd /tmp/banxe-rar-stage/wave-a-backend; timeout 600 unrar x -p"$(cat ~/.banxe/rar.pass)" -o+ /backup/banxe.rar "banxe/auth-service/*" "banxe/banxe-tx-auth/*" "banxe/banxe-identity-config-manager/*"'
```

## Stack confirmation

All three repos = **NestJS / TypeScript / Node-server** (verified via `nest-cli.json` + `package.json` markers; no Python / Go / Rust):

| Repo | `.ts` | `.tsx` | `.json` | Other markers |
|---|---:|---:|---:|---|
| `banxe/auth-service` | 11 | 0 | 6 | `nest-cli.json`, `lib/auth/*.ts`, published as `@i-link/auth-service` |
| `banxe/banxe-tx-auth` | 153 | 0 | 9 | `nest-cli.json`, `schema.graphql`, `docker-compose.yml`, Passport JWT + Redis + RabbitMQ |
| `banxe/banxe-identity-config-manager` | 5 | 0 | 8 | `nest-cli.json`, `src/app.module.ts`, `src/config/typeorm.config.ts` |

**Critical implication:** EMI is a **Python (FastAPI)** stack — `services/auth/auth_application_service.py`, `services/auth/sca_service.py`, `services/auth/two_factor.py` are all Python. Cross-language porting means **no PASS verdicts are physically possible** in this Wave (PASS = "drop-in adapter" presumes same-language fragment). Every retained fragment must be REWRITE.

This is the second architectural-fit finding in Wave A and is canon-recorded here.

---

## Top-15 backend entry points — classification with real code review

`grep -rilE "(jwt|oauth|totp|verify_password|login_handler|refresh_token|2fa|otp|hash_password|bcrypt|argon2|hmac|sca)" --include="*.py" --include="*.go" --include="*.js" --include="*.ts"` over staging produced 26 matching files; top-15 by keyword density below. Entries 13–15 had count=0 (filename-only matches that fell through filtering); legitimate top tier is rows 1–12.

Verdicts derived from `head -100 <file>` inspection on evo1, not from filename alone.

| # | File | Matches | Verdict | Rationale (from head -100) |
|---:|---|---:|---|---|
| 1 | `banxe-tx-auth/src/redis/redis-currencies.service.ts` | 5 | REJECT | Redis cache for currency rates; "verify" matched cache-key naming (`verify_*`), no auth logic. EMI uses its own currency layer. |
| 2 | `banxe-tx-auth/.eslintrc.js` | 5 | REJECT | ESLint config; matches via regex patterns in `no-restricted-syntax` rules. Tooling, not auth. |
| 3 | `banxe-tx-auth/src/redis/redis.service.ts` | 4 | REJECT | Generic Redis wrapper; no auth-specific logic. EMI has equivalent. |
| 4 | `banxe-tx-auth/src/auth/strategy/jwt.strategy.ts` | 4 | **REWRITE** | NestJS Passport `JwtStrategy.validate()` returning `{userId: payload.sub, role: payload.role, status: payload.status, service: payload.service}`. Claims schema is portable; reimplement as Python `services/auth/jwt_strategy.py` behind `TokenManagerPort.validate()`. JWKS-aware. |
| 5 | `banxe-identity-config-manager/.eslintrc.js` | 4 | REJECT | Tooling config. |
| 6 | `auth-service/.eslintrc.js` | 4 | REJECT | Tooling config. |
| 7 | `banxe-tx-auth/src/redis/redis-addresses.service.ts` | 3 | REJECT | Redis cache for crypto addresses; not auth. |
| 8 | `banxe-tx-auth/src/auth/auth.module.ts` | 2 | REJECT | NestJS framework wiring (`PassportModule.register({defaultStrategy: 'jwt'})`); EMI uses FastAPI `Depends` — equivalent already exists. |
| 9 | `banxe-tx-auth/src/rabbitmq-external/dtos/crypto-transaction-payload.dto.ts` | 1 | REJECT | RabbitMQ DTO; out of AUTH/IAM scope (belongs to Wave E crypto). |
| 10 | `banxe-tx-auth/src/auth/interfaces/jwks.interface.ts` | 1 | **REWRITE** | RFC-7517 JWKS / JWK / CompleteJwt TypeScript interfaces (`{kid, alg, kty, e, n, use}`). Port to pydantic `JwksKey`/`Jwk`/`CompleteJwt` in `services/auth/jwks_models.py`. Type-only translation, low risk. |
| 11 | `banxe-tx-auth/src/auth/guard/role.guard.ts` | 1 | **REWRITE** | NestJS `CanActivate` extracting `Bearer` token, decoding JWT, checking `user.role ∈ allowed_roles ∧ user.status == ACTIVE`. Business invariant is portable; reimplement as FastAPI dependency in `services/auth/guards/role_guard.py` behind `IAMPort.check_role(user, roles)`. |
| 12 | `banxe-tx-auth/src/auth/guard/auth.guard.ts` | 1 | REJECT | Wraps Passport's `AuthGuard('jwt')` for GraphQL `ExecutionContext` + `CurrentUser` / `CurrentIp` param decorators. NestJS-specific; FastAPI equivalents already exist (`Depends(get_current_user)`). |
| 13 | `banxe-tx-auth/src/transfers/transfers.service.ts` | 0 | REJECT | Filename-only match. Out of Wave A scope (transfers ⇒ Wave C payments). |
| 14 | `banxe-tx-auth/src/transactions/graphql/types/transaction.type.ts` | 0 | REJECT | Filename-only match. Out of Wave A scope (transactions ⇒ Wave C / E). |
| 15 | `banxe-tx-auth/src/shared/constants/common.constant.ts` | 0 | REJECT | Filename-only match; constants file. |

Verdict tally: **PASS: 0** | **REWRITE: 3** | **REJECT: 12** | **REVIEW: 0**.

### Verdict criteria (from Phase 3 roadmap)

- **PASS:** clean business logic without legacy stack ties, ready to attach via adapter behind a port.
- **REWRITE:** logic is relevant but bound to legacy stack → reimplement on top of port.
- **REJECT:** outdated or duplicates existing EMI canon.
- **REVIEW:** requires manual inspection before a decision.

---

## Top-3 PASS-candidates → become Top-3 REWRITE-candidates

PASS is structurally impossible across the NestJS→FastAPI language gap. The three highest-value REWRITE candidates (functionally equivalent to PASS for adapter-seam planning) are:

### 1. `banxe-tx-auth/src/auth/strategy/jwt.strategy.ts` → `services/auth/legacy/jwt_strategy.py`
- **Source logic:** Passport JWT strategy, JWKS-aware, returns claims dict `{userId, role, status, service}`.
- **EMI target:** new module `services/auth/legacy/jwt_strategy.py` providing `LegacyJwtStrategy.validate(token) -> ClaimsDict`.
- **Port binding:** `TokenManagerPort.validate(token)` consumes `LegacyJwtStrategy.validate`.
- **Risk:** low — RFC-7519 / RFC-7517 standards are language-agnostic. Reuse `pyjwt` + `jwcrypto` as Python equivalents.
- **Test contract:** parity test with one fixture JWT signed by the same kid and JWKS, expect equal claims dict.

### 2. `banxe-tx-auth/src/auth/interfaces/jwks.interface.ts` → `services/auth/legacy/jwks_models.py`
- **Source logic:** TypeScript interfaces only (`Jwks`, `Jwk`, `CompleteJwt`).
- **EMI target:** pydantic models in `services/auth/legacy/jwks_models.py`.
- **Port binding:** referenced by `TokenManagerPort.fetch_jwks()` and `JwtStrategy.validate()`.
- **Risk:** trivial — pure type translation, no runtime behaviour.
- **Test contract:** validate one JWKS sample loads correctly into pydantic models.

### 3. `banxe-tx-auth/src/auth/guard/role.guard.ts` → `services/auth/legacy/role_guard.py`
- **Source logic:** extract Bearer token → decode JWT → check `role ∈ allowed ∧ status == ACTIVE`.
- **EMI target:** `services/auth/legacy/role_guard.py` providing FastAPI dependency `require_roles(*roles)`.
- **Port binding:** `IAMPort.check_role(user, roles)` calls into role_guard helper.
- **Risk:** low–medium — business invariant is simple boolean; care needed around GraphQL-vs-REST extraction (EMI is REST-only currently, so simpler than source).
- **Test contract:** unit tests on `require_roles` decorator with active/inactive user × allowed/disallowed role matrix.

---

## Adapter seam plan (next step)

Open `services/auth/legacy/` package (new) with three files mirroring the REWRITE-3 above:

```
services/auth/legacy/
├── __init__.py
├── jwt_strategy.py       # LegacyJwtStrategy.validate(token) -> dict
├── jwks_models.py        # pydantic Jwks / Jwk / CompleteJwt
└── role_guard.py         # require_roles(*roles) FastAPI dependency
```

Wire-up:
- `services/auth/auth_application_service.py` keeps current login/refresh; `LegacyJwtStrategy` becomes a `TokenManagerPort` adapter for tokens issued by the legacy NestJS pipeline.
- `services/auth/iam_port.py` (existing) gains a `check_role` method backed by `role_guard.require_roles`.
- `api/routers/auth.py` is **not modified** — router stays transport-only (AUTH_IMPORT_ORDER canon). All seam wiring lives in `services/auth/`.

Exit criteria for Wave A backend:
- 3 REWRITE files implemented with parity tests vs source claim schema.
- ≥ 80 % coverage on the new `services/auth/legacy/` package.
- IL entry recording PASS/REWRITE/REJECT counts per repo.
- No router edits.

---

## Canon rules carried forward

1. **No direct BANXE.RAR import into `api/routers/auth.py`** — verified `git diff origin/main -- api/routers/auth.py` empty.
2. **All legacy attach points behind ports/adapters only** — `TokenManagerPort` / `IAMPort` / `TwoFactorPort` are the seams.
3. **PASS / REWRITE / REJECT / REVIEW** decisions recorded above with file-level rationale from real code review.
4. **Local-first** — `/tmp/banxe-rar-stage/wave-a-backend` content stays on evo1; only paths + classification land in repo.
5. **Append-only IL** — entry recorded by this session doc; exit IL entry will be added at Wave A close.
6. **Per-wave exit criteria** — adapter seams behind ports, parity tests, coverage ≥ 80 % on changed services.
