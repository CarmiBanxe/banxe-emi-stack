# GITNEXUS-PHASE1-EMI-STACK-CODE-CONTOUR — impact contour wiring (emi-stack only)

> **STATUS: PROPOSED (same singleton PR as PHASE0).** ⚠ SANDBOX / TRAINING.
> **Pointer-first (ADR-102):** fleet directive = `banxe-architecture/docs/canon/
> GITNEXUS-CODE-CONTOUR-DIRECTIVE.md` (enrich → impact → act, fail-closed). This file
> records ONLY the emi-stack deltas.

## What PHASE1 wires in this repo

- `.githooks/pre-commit.gitnexus` → `gitnexus_guard` (sandbox/license fail-closed) →
  `scripts/gitnexus/detect_impact.py` over **staged files only** (fast, stdlib).
- Fail-closed rule: staged **CRITICAL** paths without `GITNEXUS_ACK=1` ⇒ commit refused.
  **HIGH** ⇒ warning. Else informational summary only.
- Opt-in activation: the ACTIVE `.githooks/pre-commit` chain-calls the GitNexus hook
  **only when `GITNEXUS_PRECOMMIT=1`** — default behaviour is byte-identical to before.

## Delta vs banxe-architecture phase1 (deliberate)

| Aspect | architecture phase1 | emi-stack PHASE1 (this) |
|---|---|---|
| Engine delegation | delegates to `gitnexus` CLI when MCP live | **never** — structural only (bootstrap constraint: no external engine calls) |
| Risk source | graph blast-radius (or 78/EX_CONFIG) | `risk="STRUCTURAL"` always; NO-MOCK preserved (graph risk is never simulated) |
| High-risk set | fleet globs (bank-rooms, schemas, sql) | emi-stack domains (below) |

## Criticality map (structure only — no authority; ADR-130/127)

Derived from `.claude/rules/compliance-boundaries.md` domains:

- **CRITICAL** (fail-closed): `alembic/versions/`, `services/*/migrations/`,
  ledger-core (`services/ledger|banking-engine|payment*`), compliance-aml
  (`aml|kyc|sanctions_screening|adverse_media|fraud|case_management|hitl`),
  safeguarding-recon (`recon|safeguarding*|statements|client_statements`),
  reporting-fca (`services/reporting`, `dbt/`), audit-append-only (`audit_trail|audit`).
- **HIGH** (warn): `infra/`, `deploy/`, `.semgrep/`, `.githooks/`, `.github/`,
  `ledger/`, `docs/canon/`, `.claude/`, `api/`, `services/*/contracts|api`, `banxe_mcp/`, `agents/`.
- **MEDIUM/LOW**: remaining `services/`, `frontend/`, `scripts/` / `tests/`, `docs/`.

Full machine-readable map: `CATEGORY_MAP` in `scripts/gitnexus/detect_impact.py`
(single source of truth; first-match-wins globs).

## Invariant compliance

- **I-24 append-only:** PR adds files + one new ledger shard; no IL record modified.
- **I-27 HITL:** the gate PROPOSES refusal; the operator overrides explicitly
  (`GITNEXUS_ACK=1`) — no autonomous decision.
- **I-08 / audit:** no retention or audit-table changes; hook is local-only.
- **§71–§74:** single-writer, one atomic PR, pre-flight = PHASE0 checklist.

## Out of scope (explicitly NOT here)

MCP connection (template only), reindex/enrich hooks, CI `detect_impact` gate,
org-contour (phase3), any runtime AI agent — all deferred to the fleet PROD-gate
sprint after the STEP15 license fork is resolved.
