# GITNEXUS-PHASE0-EMI-STACK-VERIFY — bootstrap verification (emi-stack only)

> **STATUS: PROPOSED (singleton PR).** ⚠ SANDBOX / TRAINING (BANXE_ENV=sandbox,
> data_class=TRAINING, PROD_READY=false).
> **Pointer-first (ADR-102):** system-wide GitNexus canon lives in
> `banxe-architecture/docs/canon/GITNEXUS-CODE-CONTOUR-DIRECTIVE.md` (STEP14, IL-1102)
> and the GITNEXUS01 phase1/2/3 docs there. This file records ONLY what PHASE0 means
> for **banxe-emi-stack** — no restatement of the fleet directive.

## PHASE0 scope (this repo)

Verification + environment + inert hook + config layout. **No runtime engine, no MCP
connection, no AI agent activation.**

| Artifact | Path | State at PHASE0 |
|---|---|---|
| Env guard | `scripts/gitnexus/gitnexus_env.sh` | sandbox-only fail-closed guard; MCP probe is informational |
| Impact contour | `scripts/gitnexus/detect_impact.py` | structural-only, stdlib, no engine calls |
| Hook | `.githooks/pre-commit.gitnexus` | present but **inert** — opt-in via `GITNEXUS_PRECOMMIT=1` (README §GitNexus hook) |
| MCP template | `config/gitnexus/mcp.gitnexus.template.json` | template only; operator applies manually |
| Ledger | `ledger/entries/gitnexus01-emi-bootstrap/` | new append-only shard (I-24: nothing modified) |

## Verify checklist (operator, read-only)

1. `bash -n .githooks/pre-commit.gitnexus scripts/gitnexus/gitnexus_env.sh` — syntax OK.
2. `python3 scripts/gitnexus/detect_impact.py --files services/ledger/x.py` — prints
   structural summary, exits 1 without `GITNEXUS_ACK=1` (fail-closed proof).
3. `python3 scripts/gitnexus/detect_impact.py --files docs/README.md` — exits 0.
4. Normal commit WITHOUT `GITNEXUS_PRECOMMIT=1` — existing gate behaviour unchanged.
5. `python3 -c "import json;json.load(open('config/gitnexus/mcp.gitnexus.template.json'))"` — valid JSON.

## Boundaries

- **Perimeter (ADR-117):** everything here is scoped to this repo root; the MCP template
  pins `--repo-root` to the emi-stack checkout. No cross-repo indexing.
- **License gate:** GitNexus is PolyForm-Noncommercial-1.0.0 — sandbox only. PROD
  enablement is blocked by `banxe-architecture` STEP15 PHASE0-VERIFY (license fork
  O1/O2/O3) — operator decision, out of this repo's scope.
- **No authority mapping (ADR-130/127):** `detect_impact.py` encodes directory structure
  only; human authority stays in `.claude/rules/agent-authority.md`.

*Singleton PR, single-writer (§71–§74). Rollback: revert the PR — no state outside git.*
