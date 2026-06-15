# ADR-029: OtpDeliveryPort — OTP Lifecycle Port for Auth Domain

## Status
Proposed — 2026-05-07

## Context

Wave B of the REWRITE-1 migration scope extracts OTP (one-time password) delivery
semantics from `banxe-common/code.service.ts` into a typed Python Protocol so that
the auth domain can operate without the legacy gRPC notification microservice.

### Upstream service — `code.service.ts`

| TS method | Purpose | Mapped port method |
|-----------|---------|-------------------|
| `randomString(5)` + `codeRepository.save()` | Crypto-secure code generation + persistence | `generate_otp()` + `send_otp()` |
| `sendCode(type, destination)` | Dispatch OTP to channel (SMS / email) | `send_otp()` |
| `checkCode(codeId, code)` | Validate submitted code | `verify_otp()` |
| `retryDelay` placeholder | Rate-limit check before resend | `can_resend()` |

### What is deliberately OUT OF SCOPE

- `createApolloClient` / `registerDevice` — NotificationPort concern
- gRPC `notification` calls — infrastructure, separate adapter
- `addCredentials` after verify — `AuthApplicationService` concern
- TOTP (`generate2FAToken`) — already behind `TwoFactorPort` (ADR-015, Wave B Step 1)

### Constraints

- **ADR-015**: Auth domain uses Protocol + Adapter pattern; no direct service coupling.
- **ADR-025 §15**: Adapters for legacy services must map 1-to-1 semantically, then drop
  transport (gRPC / Apollo) and re-implement locally.
- **ADR-025 §16**: REWRITE-1 adapters use in-memory backends; production adapters
  (Twilio SMS, SendGrid email) are separate steps registered in the same port.
- **AUTH_IMPORT_ORDER**: `otp_delivery_port` imports nothing from `services.auth.legacy`;
  `legacy_otp_adapter` imports from `services.auth.otp_delivery_port` only.

## Decision

Introduce `OtpDeliveryPort` as a `@runtime_checkable` Protocol with four methods:

```
generate_otp(*, length, alphabet) -> str
send_otp(*, channel, target, code, ttl_seconds) -> OtpDeliveryReceipt
verify_otp(*, channel, target, code) -> OtpVerifyResult
can_resend(*, channel, target, min_interval_seconds) -> ResendCheck
```

Three frozen Pydantic models carry the domain data across the port boundary:

| Model | Purpose |
|-------|---------|
| `OtpDeliveryReceipt` | Confirmation that OTP was registered (delivery_id, channel, target, sent_at, expires_at) |
| `OtpVerifyResult` | Outcome of a verification attempt (success, message, delivery_id?) |
| `ResendCheck` | Rate-limit gate result (can_resend, seconds_remaining, last_sent_at?) |

### REWRITE-1 adapter — `LegacyOtpAdapter`

Location: `services/auth/legacy/legacy_otp_adapter.py`

- Backed by an in-memory dict keyed by `(channel, target)` — sufficient for dev/test
  and single-process staging before a Redis adapter is introduced.
- OTP generation uses `secrets.choice` over a deterministic alphabet (NIST SP 800-63B
  disallows math.random equivalents).
- Verification consumes the OTP on success (replay prevention via single-use semantics).
- Expired records remain in store until a new `send_otp` replaces them; `verify_otp`
  rejects them with `OtpVerifyResult(success=False, message="OTP expired")`.
- `can_resend` computes elapsed time from `sent_at`; returns `seconds_remaining=0`
  when no record exists (first send always allowed).

### Channel stubs

`channel: Literal["sms", "email"]` is stored and returned in the receipt. No network
call is made — channel routing is the responsibility of the production adapter
(TwilioOtpAdapter / SendGridOtpAdapter), not of the port or the legacy adapter.

## Consequences

### Positive

- Auth domain can generate and verify OTPs without gRPC or third-party network deps.
- Production adapters (Twilio, SendGrid) can be hot-swapped behind the same port
  without touching `AuthApplicationService` or `SCAService`.
- 100 % testable in-process: no network, no timer mocks required for happy-path.
- Replay attack surface reduced: OTP is consumed on first successful verify.

### Negative / Risks

- In-memory store is not durable; process restart clears pending OTPs. Acceptable for
  REWRITE-1; Redis adapter (Wave C) will resolve durability.
- No explicit lock on the in-memory dict; unsafe under concurrent ASGI workers. Scope
  limitation documented; production path uses atomic Redis operations.

## Alternatives Considered

| Alternative | Rejected reason |
|-------------|----------------|
| Reuse `TwoFactorPort` for OTP delivery | Wrong abstraction — TOTP and OTP delivery are independent concerns; merging violates single-responsibility |
| Emit events to notification gRPC service | Requires gRPC transport dropped per ADR-025 §15-16; out of EMI Python scope |
| Free-function module (no Protocol) | Breaks Protocol DI pattern mandated by ADR-015; un-swappable without DI injection |

## Canon

- ADR-015 (Auth Ports Formalization)
- ADR-025 §15-16 (REWRITE-1 adapter constraints)
- AUTH_IMPORT_ORDER (import discipline for services/auth/)
- `services/auth/otp_delivery_port.py` (port definition)
- `services/auth/legacy/legacy_otp_adapter.py` (REWRITE-1 adapter)
- `tests/test_otp_delivery_port.py`, `tests/test_legacy_otp_adapter.py`
