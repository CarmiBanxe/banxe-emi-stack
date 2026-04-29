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
Purpose: SCA challenge lifecycle contract for auth orchestration
Caller: AuthApplicationService or higher auth orchestration layer
Rule: SCA policy stays below transport and coordinates factor-specific capabilities through dedicated ports/adapters

### TwoFactorPort
Purpose: OTP/TOTP capability contract
Caller: SCA/auth orchestration layer
Implementation candidate: services/auth/two_factor.py::TOTPService
Rule: factor-specific logic stays below SCA orchestration

### IAMPort
Purpose: external/internal IAM identity operations
Caller: AuthApplicationService and auth-domain services
Rule: imported IAM logic attaches as adapter, not inside router

## Import rules
- No direct import into api/routers/auth.py
- Prefer adapter replacement or adapter extension behind existing ports
- Keep AuthApplicationService dependent on contracts, not imported vendor logic
- Extend ports only when required capability is not representable by current contract

## Router/SCA note
- `ScaServicePort` is currently injected directly into the router for SCA endpoints.
- Sprint 4-5 candidate: introduce an SCA application boundary so the router stops coordinating SCA-specific branching.
