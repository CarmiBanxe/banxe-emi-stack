# SESSION-2026-05-06 — BANXE.RAR smart refactor roadmap canon

## Status at audit point
- Audit of the BANXE.RAR smart-refactor branch is completed via shell.
- Source canon confirmed by repo state:
  - ADR-015 auth ports
  - AUTH_MATRIX.md
  - AUTH_IMPORT_ORDER.md
  - AUTH_REFACTOR_TASKS.md
  - AUTH_PHASE_A_INVENTORY.md
- As of 2026-05-06, the branch is an architectural preparation and import canon.
- No BANXE.RAR code is yet imported into EMI auth/services core.
- Phase A is CLOSED: login/refresh already extracted into AuthApplicationService.

## Canon rules for execution
1. No direct BANXE.RAR import into api/routers/auth.py.
2. No mixed router/service ownership for JWT or SCA policy.
3. All BANXE.RAR imports must attach behind existing or explicitly introduced ports/adapters.
4. Every imported fragment must end as one of:
   - PASS (adopt with adapter),
   - REWRITE (preserve process, rewrite implementation),
   - REJECT (not relevant or violates invariants).
5. RAR processing remains local-first on server; no cloud upload before refactor/anonymization.

## Execution order

### Phase 1 — auth boundary stabilization
Goal: finish import-ready auth boundary before touching BANXE.RAR code.

Steps:
1. Continue Sprint 4 on branch sprint4/sca-application-boundary.
2. Extract SCA orchestration from api/routers/auth.py into application/service layer.
3. Route token issuance through TokenManager boundary only.
4. Wire TwoFactor through dedicated port boundary.
5. Raise SCA and 2FA coverage to import-ready level.
6. Keep router transport-only.

Exit criteria:
- No direct SCA business logic in router.
- Token, IAM, SCA, 2FA seams are explicit and test-covered.
- Coverage/evidence recorded.

### Phase 2 — adapter seam formalization
Goal: create explicit BANXE.RAR attach points.

Steps:
1. Confirm TokenManagerPort attach seam for legacy token logic.
2. Confirm IAMPort attach seam for legacy IAM logic.
3. Confirm selective seam for BANXE.RAR SCA flow into sca_service boundary.
4. Confirm selective seam for BANXE.RAR 2FA flow below SCA orchestration.
5. Record all attach points in canonical matrix/docs.

Exit criteria:
- Each target seam has owner, target file, and contract.
- No attach point depends on router coupling.

### Phase 3 — controlled BANXE.RAR inventory
Goal: inspect legacy archive on first server and classify reusable logic.

Inventory scope:
- auth entrypoints
- JWT/token issuing/refresh/validation
- IAM integrations
- SCA / MFA / TOTP flows
- KYC / compliance hooks
- payments / reconciliation / audit processes
- orchestration / cron / workflow fragments
- notifications / openbanking / compliance side domains

For each fragment record:
- source path/module
- business role
- EMI target boundary
- PASS / REWRITE / REJECT
- security notes
- dependency/risk notes

Exit criteria:
- Legacy inventory table exists.
- Every candidate process is mapped to EMI target or rejected explicitly.

### Phase 4 — migration waves
Goal: migrate only relevant legacy processes in controlled order.

Wave A — auth / token / IAM
- token lifecycle
- auth entry orchestration
- IAM integration glue

Wave B — SCA / 2FA
- challenge / verify / resend / methods
- OTP/TOTP factor logic
- recovery and device trust policies if relevant

Wave C — payments / compliance hooks
- payment auth guards
- safeguarding/reconciliation touchpoints
- audit/compliance side effects relevant to EMI

Wave D — adjacent domains
- notifications
- openbanking
- compliance coverage wave
- only if attach points exist and relevance is confirmed

Wave E — process orchestration
- cron/workflow/n8n/business process logic from BANXE.RAR
- import only when mapped to EMI architecture and invariants

Exit criteria per wave:
- Imported logic attached behind seam.
- Tests updated and passing.
- Coverage updated.
- Session doc + matrix updated.
- PASS/REWRITE/REJECT decisions recorded.

### Phase 5 — consolidation
Goal: remove temporary duplication and finalize canonical architecture.

Steps:
1. Eliminate duplicate temporary logic after adapter cutover.
2. Freeze surviving seams as source-of-truth contracts.
3. Update docs/roadmap/handoff for next sprint.
4. Record remaining deferred items as explicit gaps.

Exit criteria:
- EMI code owns final flow.
- Legacy-derived logic exists only behind stable contracts.
- No undocumented coupling remains.

## Working rule for Perplexity / Claude in this branch
This roadmap is the execution canon for the BANXE.RAR smart-refactor stream
for both Perplexity and Claude operating in this branch.
Default next action after committing this file:
1. commit + push roadmap canon,
2. switch execution focus to sprint4/sca-application-boundary,
3. complete import-ready auth boundary before legacy code migration.

