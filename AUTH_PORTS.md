# Auth/IAM Ports

## Inbound adapter
### api/routers/auth.py
Purpose: HTTP transport adapter for auth endpoints
Caller: external HTTP clients
Rule: maps request/response only; delegates use cases inward

## Application boundary
### services/auth/auth_application_service.py
Purpose: login/refresh orchestration boundary
Caller: auth router
Rule: coordinates auth use cases and depends on contracts, not vendor logic

## Outbound ports

### TokenManagerPort
Purpose: issue access tokens, validate refresh tokens, rotate token pairs
Caller: AuthApplicationService
Rule: router must not encode/decode JWT directly

### ScaServicePort
Purpose: initiate challenge, verify challenge, resend challenge, list methods
Caller: AuthApplicationService
Rule: SCA policy stays below transport and above factor-specific adapters

### TwoFactorPort
Purpose: OTP/TOTP generation and verification
Caller: SCA/auth orchestration layer
Rule: factor-specific logic stays below SCA orchestration

### IAMPort
Purpose: external/internal IAM identity operations
Caller: AuthApplicationService and auth-domain services
Rule: imported IAM logic attaches as adapter, not inside router

## Import rules
- No direct import into `api/routers/auth.py`.
- Prefer adapter replacement or adapter extension behind existing ports.
- Keep `AuthApplicationService` dependent on contracts, not imported vendor logic.
- Extend ports only when required capability is not representable by current contract.
