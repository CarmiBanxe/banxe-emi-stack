# Next Session Start — Sprint 4 (auth-orchestration continuation)

## Status
Sprint 3 ✅ DONE (commit b8fc975 → 65da180, 2026-04-28).

## Sprint 4 Scope

### Track A — SCA Application Boundary
Goal: extract SCA orchestration from api/routers/auth.py into a dedicated
application service, mirroring the Sprint 3 pattern for login/refresh.

Concrete tasks:
1. Create services/auth/sca_application_service.py with ScaApplicationService
   that depends on ScaServicePort and (where applicable) TwoFactorPort
2. Move SCA endpoint logic (challenge / verify / resend / methods) out of
   api/routers/auth.py; keep router as thin transport mapping
3. Remove jwt.encode from services/auth/sca_service.py:434 — route token
   issuance through TokenManagerPort or a dedicated SCA token boundary
4. Wire services/auth/two_factor_port.py (currently 0% coverage) to
   services/auth/two_factor.py::TOTPService
5. Raise SCA coverage 40% -> >=80%, 2FA coverage 38% -> >=80%

Acceptance:
- api/routers/auth.py contains no SCA business branching
- ScaApplicationService is the only orchestrator of SCA challenge lifecycle
- Tests pass; pre-commit auditor green; semgrep + bandit clean

### Track B — Domain Coverage Waves (parallel)
Existing wave plan retained from Sprint 3 PLAN:
- Wave 1: notifications
- Wave 2: openbanking
- Wave 3: payments
- Wave 4: compliance

For each wave: run domain tests, inspect coverage, patch only the active
domain, re-run focused tests + coverage.

## Branching
Continue on sprint3/auth-orchestration or open sprint4/sca-application-boundary
(decision pending). Roadmap status already reflects DONE; merging Sprint 3 to
main can happen before or after Sprint 4 work.

## Reference artefacts
- AUTH_MATRIX.md — migration matrix
- AUTH_PORTS.md — port boundaries
- AUTH_PHASE_A_INVENTORY.md — closed inventory
- AUTH_REFACTOR_TASKS.md — phase checklist
- AUTH_IMPORT_ORDER.md — import ordering rules
