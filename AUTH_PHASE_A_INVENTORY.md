# Auth Phase A Inventory

## Status
Phase A inventory closed — extraction to AuthApplicationService already completed in Sprint 3 (see api/routers/auth.py:5).

## Sources
- api/routers/auth.py (187 lines, thin router)
- services/auth/auth_application_service.py (login/refresh orchestration)
- services/auth/token_manager.py (TokenManager: issue/validate/rotate/inactivity)
- services/iam/iam_port.py (IAMPort Protocol + RBAC matrix, FCA SM&CR)

## Findings
- No inline JWT encode/decode remaining in api/routers/auth.py
- login endpoint (lines 74-92) delegates to auth_app.login()
- refresh endpoint (lines 110-118) delegates to auth_app.refresh()
- Router maps AuthApplicationError -> HTTPException via _ERROR_CODE_TO_HTTP (lines 51-62)
- TokenManager exposes reusable methods: issue_access_token, issue_refresh_token, validate_access_token, validate_refresh_token, rotate, is_inactive
- IAMPort defines authenticate / validate_token / authorize / health; RBAC via BanxeRole + Permission enums

## Next phase
Proceed to Phase C — import readiness (adapter seams for BANXE.RAR auth/IAM logic via ports only).
