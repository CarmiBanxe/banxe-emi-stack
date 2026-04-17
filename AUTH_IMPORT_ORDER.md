# Auth Import Order

## Ordered steps
1. Thin auth router boundary
2. Token manager integration seam
3. IAM adapter behind IAMPort
4. Selective SCA import into sca_service boundary
5. Selective 2FA import below SCA orchestration

## Rules
- No direct BANXE.RAR import into api/routers/auth.py
- No mixed router/service JWT ownership
- No SCA policy inside transport layer
- No factor-specific logic inside router
- IAM integration attaches through IAMPort-compatible adapter only

## Why this order
- Router must become a transport boundary first
- Token issuance/refresh must move before wider auth import
- IAM contract should stabilize before adapter attachment
- SCA should remain orchestration-level, not transport-level
- 2FA should stay below SCA as implementation detail
