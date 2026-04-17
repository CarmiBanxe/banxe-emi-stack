# Auth Import Order

1. Thin auth router boundary
2. Token manager integration seam
3. IAM adapter behind IAMPort
4. Selective SCA import into sca_service boundary
5. Selective 2FA import below SCA orchestration

## Explicit non-goals
- No direct BANXE.RAR import into api/routers/auth.py
- No mixed router/service JWT ownership
- No SCA policy inside transport layer
