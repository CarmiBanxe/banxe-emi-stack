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
