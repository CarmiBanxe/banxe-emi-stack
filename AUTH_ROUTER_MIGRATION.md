# Auth Router → TokenManager Migration Delta

Scope: api/routers/auth.py
Target: services/auth/token_manager.py (TokenManager)

## Replace in login()
- line 150 jwt.encode access_payload -> token_manager.issue_access_token(customer_id)
- lines 166-175 jwt.encode refresh_payload -> token_manager.issue_refresh_token(customer_id)

## Replace in refresh_token_endpoint()
- lines 213-224 jwt.decode + manual checks -> token_manager.validate_refresh_token(body.refresh_token)
- lines 226-245 re-issue pair -> token_manager.rotate(body.refresh_token)

## Keep in router
- HTTP transport, request/response models
- HTTPException mapping (map TokenValidationError to 401)
- best-effort AuthSession persistence (can move to service layer later)

## Guardrails
- Role mapping must respect services/iam/iam_port.py ROLE_PERMISSION
- No direct JWT encode/decode in router after migration
- No direct BANXE.RAR import into api/routers/auth.py
