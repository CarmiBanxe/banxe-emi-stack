#!/usr/bin/env bash
set -euo pipefail

cat > NEXT_SESSION_START.md <<'EOF'
# Next Session Start — Auth/IAM Import Architecture

## Goal
Построить матрицу миграции и формализовать порты для осмысленного импорта кода из BANXE.RAR в BANXE EMI Stack.

## Facts already confirmed
- api/routers/auth.py содержит inline JWT login/refresh logic
- services/auth/token_manager.py exists but remains effectively unused in auth flow
- services/auth/sca_service.py and services/auth/two_factor.py have active test contour
- services/iam/iam_port.py is the strongest current contract candidate

## First actions
1. Fill AUTH_MATRIX.md for:
   - auth router
   - token manager
   - sca service
   - two factor
   - iam port
2. Fill AUTH_PORTS.md with responsibilities and boundaries
3. Decide where imported BANXE.RAR auth code should attach:
   - router level? no
   - service level? maybe
   - port/adaptor level? preferred
EOF

cat > AUTH_MATRIX.md <<'EOF'
| old path | new path | status | action | caller | role | notes |
|---|---|---|---|---|---|---|
| BANXE.RAR auth token logic | services/auth/token_manager.py | target | attach/import behind port | api/routers/auth.py | token issuance + refresh | router currently duplicates JWT logic |
| BANXE.RAR auth entry flow | api/routers/auth.py | dirty boundary | thin router only | external HTTP clients | HTTP transport layer | keep transport, move business logic out |
| BANXE.RAR SCA flow | services/auth/sca_service.py | candidate | map/import selectively | auth router / SCA endpoints | PSD2 SCA orchestration | existing tested service boundary |
| BANXE.RAR 2FA flow | services/auth/two_factor.py | candidate | map/import selectively | sca/auth service layer | OTP/TOTP factor handling | stronger than token layer today |
| BANXE.RAR IAM integration | services/iam/iam_port.py | target contract | attach adapter | auth/services layer | IAM boundary | best current contract |
EOF

cat > AUTH_PORTS.md <<'EOF'
# Auth/IAM Ports

## TokenManagerPort
Purpose: issue access tokens, validate refresh tokens, rotate token pairs
Caller: auth router
Rule: router must not encode/decode JWT directly

## ScaServicePort
Purpose: initiate challenge, verify challenge, resend challenge, list methods
Caller: auth router
Rule: SCA policy stays in service layer

## TwoFactorPort
Purpose: OTP/TOTP generation and verification
Caller: SCA service
Rule: factor-specific logic stays below SCA orchestration

## IAMPort
Purpose: external/internal IAM identity operations
Caller: auth domain services
Rule: imported IAM logic attaches as adapter, not inside router
EOF

cat > AUTH_ROUTER_MIGRATION.md <<'EOF'
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
EOF

chmod +x make_auth_docs.sh
echo "created make_auth_docs.sh"
