# SESSION-2026-05-06 — BANXE.RAR smart refactor audit

## Scope
Audit of the "smart refactor" branch for BANXE.RAR auth/IAM flows into EMI stack
(based strictly on repo state, no operator memory).

## Findings (facts)
- Phase A inventory is CLOSED: login/refresh orchestration extracted to
  services/auth/auth_application_service.py and api/routers/auth.py is a thin
  transport boundary for these paths (AUTH_PHASE_A_INVENTORY.md).
- AUTH_MATRIX.md defines canonical attach points for BANXE.RAR:
  - Router stays transport-only (no direct BANXE.RAR import).
  - TokenManager, SCAService, TwoFactor, IAMPort are the target boundaries.
- AUTH_REFACTOR_TASKS.md and AUTH_IMPORT_ORDER.md define a 3-phase plan:
  A — inventory (done), B — extraction (partially done for login/refresh),
  C — import readiness (adapter seams for BANXE.RAR auth/IAM, selective SCA/2FA).
- ADR-015-auth-ports requires BANXE.RAR adapters to implement Protocols behind
  ports (TokenManagerPort, ScaServicePort, TwoFactorPort, IAMPort), not modify
  core services directly.

## Conclusions
- No BANXE.RAR code is currently imported into services/auth/* or services/iam/*.
- The "BANXE.RAR smart refactor" branch is, as of 2026-05-06, an architectural
  canon (ports + matrices + import order), not yet a code-level migration.
- Next practical step is to continue Sprint 4 on branch
  sprint4/sca-application-boundary, wiring SCA/2FA to the defined ports and
  raising coverage to >=80%, so that BANXE.RAR SCA/2FA flows can attach via
  adapters later.

## Canon
This session is canonical per ADR-025 + IL-CANON-OPERATOR-2026-05.
