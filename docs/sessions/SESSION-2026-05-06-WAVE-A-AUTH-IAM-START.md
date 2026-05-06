# Wave A start — AUTH / IAM import from BANXE.RAR

**Date:** 2026-05-06
**Branch:** `sprint5/wave-a-auth-iam-import-2026-05-06` (from `main` @ `6874e2f`)
**Canon:** ADR-015 (auth ports) + ADR-025 §16 (shell hygiene) + AUTH_MATRIX.md + AUTH_IMPORT_ORDER.md
**Status:** OPEN — staging done, classification in progress, no legacy files committed.

---

## Stage location (NOT committed)

| Field | Value |
|---|---|
| Host | `evo1` |
| Path | `/tmp/banxe-rar-stage/wave-a` |
| Source | `/backup/banxe.rar` (SHA-256 `420913292bf38c50543cbcecd8c2079e050f8d3fc588b1f7f145605af0e1bf13`) |
| Extracted | `banxe/banxe_auth/*` + `banxe/common_auth_web/*` |
| Staging size | **70 MB** |
| File count (excl. `.git/`) | **952 regular files** |
| Listing-derived path count | 1357 (764 `banxe_auth` + 593 `common_auth_web` — incl. dirs in listing) |
| Local-first rule | RAR + extracted files remain on evo1; no cloud upload, no broader movement (ADR-025 §3.2 / canon) |
| Repo artefacts | `docs/inventories/WAVE-A-AUTH-IAM-PATHS.txt`, `docs/inventories/WAVE-A-ENTRY-POINTS-2026-05-06.txt` only |

Reproduce extraction:
```
ssh banxe@evo1 'mkdir -p /tmp/banxe-rar-stage/wave-a && cd /tmp/banxe-rar-stage/wave-a && timeout 600 unrar x -p"$(cat ~/.banxe/rar.pass)" -o+ /backup/banxe.rar "banxe/banxe_auth/*" "banxe/common_auth_web/*"'
```

Reproduce entry-point grep:
```
ssh banxe@evo1 'cd /tmp/banxe-rar-stage/wave-a && grep -rilE "(jwt|oauth|totp|verify_password|login|refresh_token|2fa|otp)" --include="*.py" --include="*.js" --include="*.ts"'
```

---

## Critical architectural finding (must surface before classification)

Both staged repos are **frontend TypeScript / React / Apollo GraphQL** — not backend auth services. Verified by extension distribution and `package.json` headers:

| Repo | Top extensions | `package.json` name | Verdict on architectural fit |
|---|---|---|---|
| `banxe/banxe_auth` | 183 `.ts` + 118 `.tsx` + 65 `.svg` + 31 `.graphql` + webpack/codegen configs | `"banxe-auth"` — *"banxe auth and kyc project"* (LLC I-Link) | Frontend SPA, **not** backend auth logic |
| `banxe/common_auth_web` | 179 `.tsx` + 91 `.ts` + 40 `.svg` + 16 `.json` | `"common_auth"` — boilerplate `git@gitlab.i-link.pro:gradesor/web-boilerplate.git` | Frontend lib, **not** backend |

**Implication:** these repos cannot attach behind `TokenManagerPort` / `IAMPort` / `TwoFactorPort` — those are backend Python ports. The architecturally correct backend AUTH/IAM candidates from the Phase 3 inventory are:

- `banxe/auth-service` (87 files)
- `banxe/banxe-tx-auth` (278 files)
- `banxe/banxe-identity-config-manager` (67 files)

Recommended action before Wave A continues: **re-scope Wave A** to include those three repos, OR split Wave A into **A1 (frontend auth UI — out-of-EMI-scope)** and **A2 (backend auth/IAM — in EMI scope)**. Decision belongs to operator; this finding is recorded as canon.

---

## Top-15 entry points — classification

12 unique files matched the auth-keyword regex (less than 15 because the staged scope is frontend-only and most logic is in GraphQL `.graphql` schema files which were excluded by the `--include` filter for `*.py|*.js|*.ts`). Verdicts reflect the **architectural-fit finding** above.

| # | File path (relative to evo1 staging) | Match count | Preliminary verdict | Rationale |
|---:|---|---:|---|---|
| 1 | `banxe/banxe_auth/src/shared/api/apollo/__generated__/index.ts` | 24 | REVIEW | Apollo-generated GraphQL types; informs **backend contract design**, not direct import. Schema may seed `services/auth/contracts/`. |
| 2 | `banxe/banxe_auth/src/pages/Login/model/index.ts` | 13 | REJECT | Frontend page model (effector store / React state) — out of EMI Python scope. |
| 3 | `banxe/common_auth_web/src/__generated__/index.ts` | 6 | REVIEW | Apollo-generated types for shared frontend lib; same rationale as #1. |
| 4 | `banxe/banxe_auth/src/features/PasswordRecovery/model/RecoveryPasswordModel.ts` | 5 | REJECT | Frontend feature model; `services/auth/auth_application_service.py` already owns the backend recovery flow. |
| 5 | `banxe/banxe_auth/src/shared/config/analitycsEnums/operationsNames.ts` | 4 | REJECT | Frontend analytics enums; not security-relevant. |
| 6 | `banxe/banxe_auth/src/shared/config/analitycsEnums/newOperationsNames.ts` | 2 | REJECT | Frontend analytics enums (newer variant). |
| 7 | `banxe/banxe_auth/src/shared/lib/checkError.ts` | 1 | REJECT | Frontend error shaping; backend already uses `AuthApplicationError` mapping. |
| 8 | `banxe/banxe_auth/src/pages/Login/ui/styles.ts` | 1 | REJECT | Linaria CSS-in-TS; out of scope. |
| 9 | `banxe/banxe_auth/src/features/PasswordRecovery/lib/parseTFAError/types.ts` | 1 | REVIEW | TFA error shape — may inform `services/auth/two_factor.py` `VerifyResult.message` taxonomy. |
| 10 | `banxe/common_auth_web/src/theme/index.ts` | 0 | REJECT | Theme tokens; no auth logic. |
| 11 | `banxe/banxe_auth/src/pages/CreatingAccount/model/index.ts` | 0 | REJECT | Frontend page model. |
| 12 | `banxe/banxe_auth/src/features/Login/index.ts` | 0 | REJECT | Frontend feature root. |

**PASS-кандидатов: 0** (architectural-fit gap).
**REWRITE: 0** (same reason).
**REVIEW: 3** (#1, #3, #9 — for contract / error-taxonomy seeding only).
**REJECT: 9.**

### Verdict criteria (from Phase 3 roadmap)

- **PASS:** clean business logic without legacy stack ties, ready to attach via adapter behind a port.
- **REWRITE:** logic is relevant but bound to legacy stack → reimplement on top of port.
- **REJECT:** outdated or duplicates existing EMI canon.
- **REVIEW:** requires manual inspection before a decision.

---

## Next step

Architectural-fit gap blocks the original adapter-seam plan. Two parallel tracks:

1. **Track A1 — frontend repos (current Wave A scope):**
   - 0 backend imports — these repos go to a **frontend EMI track** (separate `frontend/` repo or hand-off to mobile/web team), not into `services/auth/legacy/`.
   - REVIEW items #1/#3/#9 — extract GraphQL `schema.graphql` + Apollo-generated types as **contract reference** for backend `services/auth/contracts/` (read-only inspection, no copy).

2. **Track A2 — re-scoped Wave A backend (new):**
   - Open `sprint5/wave-a-backend-auth-iam-2026-05-06` from `main`.
   - Stage on evo1: `banxe/auth-service/*`, `banxe/banxe-tx-auth/*`, `banxe/banxe-identity-config-manager/*` (per Phase 3 inventory).
   - Re-run grep with `--include="*.py" --include="*.go" --include="*.js"` to capture backend logic.
   - Classify top-15 PASS/REWRITE/REJECT/REVIEW.
   - Build adapter seams under `services/auth/legacy/` behind `TokenManagerPort` / `IAMPort` / `TwoFactorPort` for PASS items.

Operator decides whether Track A1 splits to a frontend repo or stays paused, and whether Track A2 starts immediately or is sequenced after Wave A1 close.

---

## Canon rules carried forward

1. **No direct BANXE.RAR import into `api/routers/auth.py`** — router stays transport-only (AUTH_IMPORT_ORDER).
2. **All legacy attach points behind ports/adapters only** — no service-level imports outside the `services/auth/` boundary.
3. **PASS / REWRITE / REJECT / REVIEW** decision per fragment, recorded in this session doc and per-wave IL entry.
4. **Local-first** — `/tmp/banxe-rar-stage/wave-a` content remains on evo1; only paths + classification land in repo.
5. **Append-only IL** — Wave A entry + exit emit IL entries; this session doc is the entry record.
6. **Per-wave exit criteria** — adapter seams behind ports, tests updated, coverage ≥ 80 % for changed services.
