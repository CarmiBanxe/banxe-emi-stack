# [SAFE-PORT] Quality-gate scaffolding: Banxe -> Legion (OpenManus)
# PROPOSAL — Charter §10 (Proposal BEFORE implementation)
# Date: 2026-07-15
# Status: PROPOSED — awaiting operator "yes" before ANY implementation
# Ref: Phase-1 DRAFT audit §9.4 | pre-reconcile/20260714

---

## 0. TL;DR

Legion (OpenManus) has 53 test files but **no coverage threshold and no quality-gate**.
This proposal extracts the quality-gate *scaffolding pattern* from banxe and adapts it
for Legion. **Nothing is implemented by this document.** Implementation begins only after
the operator replies "yes".

---

## 1. Identification

| Field | Value |
|-------|-------|
| **Proposal ID** | PROP-2026-0714-001 |
| **Title** | [SAFE-PORT] Quality-gate scaffolding: Banxe → Legion (OpenManus) |
| **Status** | PROPOSED (awaiting operator approval) |
| **Direction** | `banxe-emi-stack` → `OpenManus` (Legion) |
| **Operation type** | EXTRACT PATTERN / ADAPT (Charter §3) |
| **Source repo** | `banxe-emi-stack` — sandbox donor |
| **Target repo** | `OpenManus` — Legion, the production engine (100% obkatan) |
| **Author** | BANXE Factory Agent |
| **Charter ref** | §3 (extract pattern), §9 (hard line: no FCA logic), §10 (proposal gate) |
| **Audit basis** | Phase-1 DRAFT audit §9 (test harnesses), §9.4 (safe-port candidate note) |

---

## 2. Context

### 2.1 Legion test maturity gap (verified 2026-07-15 02:05)

| Metric | Value |
|--------|-------|
| Test files | 53 |
| Coverage gate | **NONE** — `--cov-fail-under` not present anywhere in Legion |
| Quality-gate script | **NONE** — no `quality-gate.sh` or equivalent found |
| Semgrep in CI | Not confirmed present |
| Maturity | **EARLY-STAGE** |

Legion is the production RL/AI engine to be launched and fully obkatan (100%). The absence
of a coverage threshold and quality-gate means regressions can merge undetected. This is the
gap this proposal addresses.

### 2.2 Banxe donor pattern (verified same session)

Banxe has a production-grade quality harness:

| Artifact | Detail |
|----------|--------|
| `pyproject.toml` `[tool.pytest.ini_options]` | `addopts` includes `--cov=services --cov=api --cov=src --cov-report=term-missing --cov-fail-under=35` |
| `Makefile` | `make lint` (Ruff + Biome), `make test`, `make test-full`, `make quality-gate` (lint + semgrep + tests) |
| CI | GitHub Actions quality-gate workflow; semgrep SAST; Biome frontend lint |

### 2.3 S-18 status on Legion (context only — NOT part of this port)

Recorded here to avoid confusion with this proposal's scope:

- `config/config.toml` is **gitignored** (confirmed); live `api_key="none"`.
- `.bak` files also gitignored. Gateway key rotation is a **separate operator action (B1)**.
- Main API server binds `0.0.0.0` **inside the container** but is published only to
  `127.0.0.1` via Docker Compose (Dockerfile line 21) — S-18 §1.2 satisfied by design.
- Remaining `0.0.0.0` occurrences in vendored `verl/` and webshop demo env — to be
  confirmed as non-production paths (open item B2, separate from this proposal).

---

## 3. What Is Proposed

**Patterns only. No code verbatim. No FCA logic. No banxe-specific identifiers.**

### 3.1 Item P1 — pytest coverage threshold (pyproject.toml)

Adapt `[tool.pytest.ini_options]` in Legion's `pyproject.toml` to add a coverage threshold
and coverage reporting. Coverage targets will be **adapted to Legion's module layout**:

```toml
# PROPOSED ADAPTATION (not copied verbatim) — targets adapted for Legion:
[tool.pytest.ini_options]
addopts = "--cov=openmanus_rl --cov-report=term-missing --cov-fail-under=<THRESHOLD>"
```

- `openmanus_rl/` replaces `services/api/src/` (banxe-specific paths — not ported).
- `<THRESHOLD>` is an open question for the operator (see §6).
- `pytest-cov` must be added to Legion's dev dependencies if not already present.

### 3.2 Item P2 — Makefile `quality-gate` target

Adapt banxe's Makefile pattern to Legion. Proposed structure:

```makefile
# PROPOSED ADAPTATION (generic pattern, not banxe business logic)
lint:
	ruff check openmanus_rl/ tests/
	ruff format --check openmanus_rl/ tests/

test:
	pytest tests/ -q --tb=short

quality-gate: lint test
	@echo "Quality gate passed."
```

- Biome target is **not** included (Legion has no frontend; Biome is frontend-only).
- Ruff replaces any existing lint tool or is added if absent.
- semgrep step may be added if Legion CI already uses it (to be confirmed during implementation).

### 3.3 Item P3 — GitHub Actions CI wiring pattern

Adapt the GitHub Actions quality-gate workflow pattern from banxe. The adapted workflow:

- Triggers on `push` and `pull_request` to `main`.
- Runs `make quality-gate` (lint + tests + coverage).
- Blocking vs advisory: **open question for operator** (see §6).
- Does NOT include banxe-specific gates (Biome, FCA semgrep rules, Alembic checks).

---

## 4. What Is Explicitly NOT Ported (Charter §9 Hard Line)

The following are **categorically excluded**. No exceptions. No partial extraction.

| Category | Examples | Reason |
|----------|----------|--------|
| FCA financial invariants | I-01 (Decimal), I-02 (jurisdictions), I-24 (audit trail), I-27 (HITL) | Regulated; inapplicable outside banxe FCA context |
| Banking service logic | Ledger, payment, reconciliation, safeguarding | banxe business domain |
| Compliance business rules | AML thresholds, KYC flows, sanctions screening | Regulated; banxe-specific |
| Banxe semgrep rules | `banxe-float-money`, `banxe-audit-delete`, `banxe-clickhouse-ttl-reduce` | FCA-specific; not applicable to Legion |
| Banxe-specific pytest markers | Any custom marker tied to compliance domains | Not meaningful in Legion context |
| Banxe credentials / secrets layout | `.env.example`, secret paths, Keycloak config | Banxe infrastructure |
| FCA regulatory references | CASS 15, MLR 2017, PS22/9 etc. | inapplicable to Legion |

The ported artifacts will contain **only generic Python project scaffolding** that would be
appropriate for any professionally maintained Python repo.

---

## 5. Compliance Check

| Check | Result |
|-------|--------|
| FCA invariants crossed | **NO** — patterns only; zero FCA logic |
| Charter §9 hard line respected | **YES** — explicit exclusion list above (§4) |
| Forbidden components (Charter §8: Tor/onion/i2p/socks/anonymity) | **N/A** — not involved |
| Sanctioned jurisdictions (RU/BY/IR/KP/CU/MM/AF/VE/SY) | **N/A** — not involved |
| Semgrep expectation post-adaptation | **0 findings** — generic scaffolding only |
| Banxe main branch touched | **NO** — banxe is read-only donor; not modified |
| OpenManus main touched | **NO** — implementation in isolated worktree/branch only |

---

## 6. Open Questions for Operator

Before implementation can begin, the operator must answer:

| # | Question | Options / Notes |
|---|----------|-----------------|
| OQ-1 | **Target coverage threshold for Legion?** | Banxe uses 35%. Legion is early-stage; suggest starting at **20%** to establish a floor without failing existing tests. Operator may choose any value or "none initially". |
| OQ-2 | **CI gate: blocking or advisory initially?** | Blocking (merge fails on coverage drop) provides hard enforcement. Advisory (warnings only) lets the team ramp up. Recommendation: **advisory initially, blocking after 30 days**. |
| OQ-3 | **Semgrep in Legion CI: add or defer?** | If Legion has no semgrep today, this can be added as part of P3 (generic rules only, no banxe rules). Or defer to a follow-up proposal. |

---

## 7. Risk and Rollback

| Dimension | Assessment |
|-----------|------------|
| Change type | **Additive only** — new config entries and new CI file; no existing code deleted or modified |
| Reversibility | **Fully reversible** — remove the added config sections and delete the new workflow file |
| Blast radius | **Minimal** — affects only Legion's CI pipeline and local `make` targets |
| Backup | `pre-reconcile/20260714` annotated tag exists on Legion (`26ef51a`) — point of safe return |
| Implementation isolation | Changes go in a dedicated Legion worktree/branch; never directly on `main` |
| FCA risk | **Zero** — no FCA-regulated code is touched or ported |

---

## 8. Implementation Plan (CONDITIONAL — only after operator "yes")

**This section is informational only. Nothing below is executed until approved.**

1. Create isolated worktree/branch on Legion: `git worktree add ../openmanus-quality-gate -b feat/quality-gate`.
2. Add `pytest-cov` to `pyproject.toml` dev dependencies (if absent).
3. Edit `pyproject.toml`: add `[tool.pytest.ini_options]` with adapted addopts (threshold per OQ-1).
4. Edit / create `Makefile`: add `lint`, `test`, `quality-gate` targets.
5. Create `.github/workflows/quality-gate.yml`: adapted from banxe pattern; blocking per OQ-2 answer.
6. Run `make quality-gate` locally in the worktree and resolve any failures.
7. Open PR against Legion `main`; operator reviews and merges.
8. Remove worktree after merge.

Total estimated scope: **3–4 files changed**, **< 60 lines added**. No deletions.

---

## 9. Approval Gate

```
┌────────────────────────────────────────────────────────────────┐
│  OPERATOR ACTION REQUIRED                                      │
│                                                                │
│  Respond to this proposal with:                                │
│    "yes" — proceed with implementation (answer OQ-1 and OQ-2) │
│    "no"  — decline; proposal archived, no action taken        │
│    "defer <reason>" — pause; revisit after stated condition    │
│                                                                │
│  The factory executes NOTHING until an explicit "yes" is       │
│  received. This document changes zero files in OpenManus.      │
└────────────────────────────────────────────────────────────────┘
```

---

*BANXE Factory Agent | Reconciliation Worktree | 2026-07-15*
*Worktree: banxe-emi-stack-reconciliation-20260714 | Branch: feat/reconciliation-charter-20260714*
*Charter ref: §3 (extract pattern) · §9 (hard line) · §10 (proposal gate)*
