# Legion (OpenManus) — FINE Pass Consolidation
# TYPE: FINE (second) pass — supersedes DRAFT classifications from 2026-07-15 first pass
# Audit date: 2026-07-15 | Produced by: BANXE Factory Agent | PROP-2026-0714-001
#
# Baseline anchor: backup tag pre-reconcile/20260714 (both repos)
# Legion code ref: OpenManus-quality-gate-20260714 @ b48852c (feat/quality-gate-safe-port-20260714)
# Banxe code ref:  banxe-emi-stack @ origin/main 312ce3d (NOT the agent branch)
# Charter §9 applies throughout: no FCA logic, no banking credentials ported to Legion.

---

## 0. Purpose and Scope

This document is the **FINE (second) reconciliation pass** for the Banxe ↔ Legion (OpenManus)
SAFE-PORT programme. It supersedes the DRAFT-status open items from:

- `audit-20260714-topology-deps.md` (Phase-1 across 5 Charter dimensions — DRAFT COMPLETE)
- `audit-20260715-legion-readiness-matrix.md` (gap list G-1..G-4 — DRAFT)
- `audit-20260715-legion-match-mismatch.md` (match/mismatch + open items S-18 / 0.0.0.0)
- `audit-20260715-legion-obkatka.md` (hardening sprint A–F scorecard)

**What this pass adds:**
1. Gap closure status for G-1..G-4, guardrails (A-3), and Tor/onion compliance flag.
2. Resolution of DRAFT open items (S-18, 0.0.0.0, baseline anchoring).
3. Unified Charter-dimension status table.
4. Operator action list for the pending merge.

**What this pass does NOT change:** no code edits, no existing doc revisions, no push.

---

## 1. Hardening Sprint Context (Steps 1–3)

The hardening sprint PROP-2026-0714-001 executed three committed steps on the isolated worktree
`feat/quality-gate-safe-port-20260714`. All changes are additive-only. None are on OpenManus `main` yet.

| Step | Commit | Description |
|------|--------|-------------|
| A–F hardening | `f4cfc14` | qdrant_memory.py, guardrails/policy.py, middleware/rate_limiter.py, eval_quality_gate.py, runbooks, Tor/onion removal from roadmap |
| lint step2 | `9232060` | ruff autofix safe rules (F401/F811/etc) 25 files; F821/F841 deferred |
| gate step3 | `b48852c` | coverage floor 20% → 35%; test step BLOCKING in CI; lint/semgrep advisory |

**Push status:** NOT performed (I-71). Push + merge to OpenManus main = Step 1 operator action.

---

## 2. GAP CLOSURE TABLE

> Status key: **CLOSED-ON-BRANCH** = artifact committed, not yet on main | **PENDING-MERGE** = needs operator push/merge | **ACCEPTED-RISK** = operator-accepted, no further action | **RESOLVED** = closed by design or analysis, no code needed

### 2.1 Production-Readiness Gaps (G-1 to G-4)

| Gap | DRAFT Status (2026-07-15 first pass) | FINE Status | Evidence | Pending action |
|-----|--------------------------------------|-------------|----------|----------------|
| **G-1** Vector-store RAG absent | GAP | **CLOSED-ON-BRANCH** | `openmanus_rl/memory/qdrant_memory.py` (f4cfc14) — Qdrant backend with SQLite keyword fallback; `config/qdrant_config.yaml`; 9 tests (`tests/test_memory/test_qdrant_memory.py`) | **PENDING-MERGE** to OpenManus main |
| **G-2** Blocking eval gate absent | GAP *(intentional, Q3)* | **CLOSED-ON-BRANCH** | `scripts/eval_quality_gate.py` (f4cfc14) — exits non-zero on regression; `config/eval_gate_config.yaml`; CI test step now BLOCKING (`continue-on-error` removed, b48852c); floor raised 20%→35% | **PENDING-MERGE** to OpenManus main |
| **G-3** Rollback / runbook absent | GAP | **CLOSED-ON-BRANCH** | `docs/runbooks/rollback.md` (f4cfc14) — 8-section runbook: symptoms, state capture, code/config/Qdrant rollback, recovery verification, incident filing; `docs/runbooks/qdrant-setup.md` | **PENDING-MERGE** to OpenManus main |
| **G-4** Budget / rate-limit absent | GAP | **CLOSED-ON-BRANCH** | `openmanus_rl/middleware/rate_limiter.py` (f4cfc14) — sliding-window RPM/RPH + global RPM; wired into `agent_server.py` via `add_middleware(build_rate_limit_middleware())`; `RateLimitConfig` token-budget field (advisory, enforcement deferred to LLM-token-counting integration); 11 tests | **PENDING-MERGE** to OpenManus main |

### 2.2 Guardrails (A-3 from match-mismatch)

| Item | DRAFT Status | FINE Status | Evidence |
|------|-------------|-------------|----------|
| **A-3** NeMo Guardrails absent (Sprint 11 intent) | MATCH — both agree not done | **CLOSED-ON-BRANCH (native)** | `openmanus_rl/guardrails/policy.py` (f4cfc14) — native guardrail engine (no NeMo dependency): Tor/onion regex patterns, blocked-tool-name set, `GuardrailPolicy`, `check_request()`; wired into `/chat` and `/stream` handlers (HTTP 400 on violation); 16 tests (`tests/test_guardrails/test_policy.py`) | **PENDING-MERGE** to OpenManus main |

### 2.3 Tor / Onion Compliance Flag

| Item | DRAFT Status | FINE Status | Evidence |
|------|-------------|-------------|----------|
| **COMPLIANCE** Tor/onion in roadmap (Charter §8) | HIGH FLAG | **CLOSED** | Roadmap `DEPLOYMENT_READY_ROADMAP.md` (commit `e4f5b18`, OpenManus main): 6 Tor/onion references removed; Charter §8 immutable policy comment added at file header; `docs/NETWORK_HARDENING.md`: clarification note added (monitoring output ≠ implementation). Runtime enforcement: `guardrails/policy.py` Tor-pattern regex detector active in `/chat` and `/stream` (commit f4cfc14 on branch). |

> **Note on roadmap commit `e4f5b18`:** this commit landed on the **OpenManus main repo**
> (`/home/mmber/OpenManus`) directly, not the worktree branch. It is already on main (no merge needed).
> The guardrail runtime enforcement is on the worktree branch and requires merge.

---

## 3. DRAFT OPEN ITEM RESOLUTION

### 3.1 S-18 — Secret / API Key in `config.toml`

**DRAFT status:** HIGH — API key found in Legion `config.toml` during Phase-1 scan.

**Resolution:**

| Remediation step | Status |
|-----------------|--------|
| `config.toml` added to `.gitignore` | **DONE** — confirmed in worktree (f4cfc14 + prior commits) |
| Key value masked in logs / outputs | **DONE** — rate limiter `get_client_id()` masks to first 16 chars |
| `.bak` file added to `.gitignore` | **DONE** |
| Secret rotation | **SKIPPED** — operator-accepted risk |

**Final status: ACCEPTED-RISK**

Operator decision: rotation skipped during obkatka sprint. The key in `config.toml` is a
development/staging credential. It is gitignored and not committed to the branch. Rotation
is the operator's responsibility at next credential lifecycle event. This item requires no
further factory action.

---

### 3.2 `0.0.0.0` Bind — S-18 §1.2 Open Question

**DRAFT status:** NEEDS-OPERATOR-CONFIRMATION — three `0.0.0.0` / `[::]` binds observed:
1. `Dockerfile CMD`: `uvicorn openmanus_rl.api.server:app --host 0.0.0.0 --port 8000`
2. `verl/.../retrieval_server.py`: `uvicorn.run(host="0.0.0.0", port=8000)` — vendored
3. `verl/.../rollout/async_server.py`: `host=["::","0.0.0.0"]` — vendored

**Resolution:**

| Bind | Classification | Reasoning | Status |
|------|---------------|-----------|--------|
| `Dockerfile` main API (`0.0.0.0:8000`) | **Design-safe** | Container-internal bind; `docker-compose.yml` publishes port via `127.0.0.1` on the host — as confirmed by the `Dockerfile` comment at line 21 and the SAFE-PORT proposal §3 analysis. The container-side `0.0.0.0` is necessary for Docker networking; the host-side publish is `127.0.0.1` only. S-18 §1.2 satisfied. | **RESOLVED (design-safe)** |
| `verl/.../retrieval_server.py` | **Vendored / non-prod** | verl is a vendored training sub-library, not the production serving stack. The retrieval server is a data-parallel training helper, not a customer-facing endpoint. Not first-party code. | **RESOLVED (non-prod / vendored)** |
| `verl/.../rollout/async_server.py` | **Vendored / non-prod** | Same rationale as above. VERL rollout server is a distributed training infrastructure component, never deployed as a production API. | **RESOLVED (non-prod / vendored)** |

**Residual safeguard:** the `docker-compose.yml` `127.0.0.1` host-side publish **must be maintained**.
If compose is updated to publish on `0.0.0.0`, S-18 §1.2 would be violated. Owner: whoever
maintains `docker-compose.yml` — add a comment referencing this constraint.

**Final status: RESOLVED (design-safe)**

---

### 3.3 Baseline Anchoring — banxe non-main / OpenManus evolving HEAD

**DRAFT status (first-pass caveat):** banxe scanned on `agent/factory/ledgerenv/sandbox-fix` (worktree
noise), not main; OpenManus HEAD was moving during the audit.

**Resolution:**

| Source | Anchor used for FINE pass | Rationale |
|--------|--------------------------|-----------|
| OpenManus (Legion) | `pre-reconcile/20260714` backup tag → worktree HEAD `b48852c` | Tag preserves pre-sprint state; b48852c is the post-sprint verified clean state |
| banxe-emi-stack | `origin/main @ 312ce3d` | Canonical baseline; agent branch excluded from analysis |

This fine pass uses these anchors throughout. All FINE-pass findings are reproducible from these refs.

---

## 4. Charter Audit Dimensions — Unified Status

Five audit dimensions from Phase-1 pass (`audit-20260714-topology-deps.md §0`):

| Dimension | Phase-1 Status | FINE-Pass Status | Notes |
|-----------|---------------|-----------------|-------|
| **§8 Forbidden deps** (Tor/onion/i2p/SOCKS) | PASS (clean) → HIGH FLAG on roadmap | **CLOSED** | Roadmap purged (e4f5b18 on OpenManus main); runtime guardrail added (on branch, pending merge) |
| **Runtime entrypoints / network isolation** | DRAFT — `0.0.0.0` open question | **RESOLVED** | Main API design-safe (compose 127.0.0.1 publish); verl/webshop vendored/non-prod; see §3.2 |
| **Safety / compliance surfaces** (secrets, keys) | DRAFT — S-18 HIGH open | **ACCEPTED-RISK** | Gitignored, masked; rotation operator-deferred; no further factory action; see §3.1 |
| **Test harnesses / quality gate** | PARTIAL — advisory-only CI, 20% floor | **CLOSED-ON-BRANCH** | 524 tests, 43% coverage, 35% floor, test step BLOCKING (b48852c); pending merge to main |
| **Gap closure / production readiness** (G-1..G-4) | GAP (4 open) | **CLOSED-ON-BRANCH** | All 4 gaps addressed (f4cfc14); pending merge to OpenManus main |

**Summary:** 2 dimensions fully closed (§8 roadmap purged; 0.0.0.0 resolved); 1 accepted-risk (S-18);
2 closed-on-branch pending merge (quality gate; G-1..G-4).

---

## 5. Test & Coverage Snapshot (FINE-pass baseline, b48852c)

| Metric | Value |
|--------|-------|
| Passed | **524** |
| Skipped (env-gated) | 5 |
| Failed | 0 |
| New tests (hardening sprint) | 36 (guardrails: 16, rate limiter: 11, qdrant memory: 9) |
| Coverage (`openmanus_rl/`) | **43%** |
| Coverage floor | **35%** (raised from 20%, commit b48852c) |
| CI test step | **BLOCKING** (`continue-on-error` removed) |
| CI lint/format/semgrep | Advisory (`continue-on-error: true`) |

---

## 6. Counts Summary

| Category | Count | Items |
|----------|-------|-------|
| CLOSED (no further action) | 2 | Tor/onion compliance flag; 0.0.0.0 bind question |
| CLOSED-ON-BRANCH + PENDING-MERGE | 5 | G-1 (Qdrant RAG), G-2 (eval gate), G-3 (runbook), G-4 (rate limiter), A-3 (guardrails) |
| ACCEPTED-RISK | 1 | S-18 key rotation (operator decision) |
| RESOLVED (design / analysis) | 2 | 0.0.0.0 main API (design-safe), verl/webshop 0.0.0.0 (vendored non-prod) |
| DEFERRED (separate reviewed step) | 2 | F821 undefined-name (real bugs), F841 unused-variable |

---

## 7. Next Operator Actions (I-71 — Push / Merge Pending)

Actions required from the operator. Factory has completed all code work. No further factory action needed
until operator authorizes the push.

| # | Action | Detail | Blocker? |
|---|--------|--------|---------|
| **OP-1** | Push `feat/quality-gate-safe-port-20260714` to OpenManus fork | `git push myfork feat/quality-gate-safe-port-20260714` | Yes — hardening not on main without this |
| **OP-2** | Open PR + merge to OpenManus `main` | Merges f4cfc14, 9232060, b48852c (and prior obkatka commits) | Yes — G-1..G-4 + guardrails + quality gate |
| **OP-3** | Rebase recon branch onto `origin/main 312ce3d` | `git rebase origin/main` in `banxe-emi-stack-reconciliation-20260714`; then push | Required (branch is behind main) |
| **OP-4** | Push + merge `feat/reconciliation-charter-20260714` | Delivers recon audit docs to banxe-emi-stack main | Required to land this doc |
| **OP-5** | Rotate S-18 credential (deferred) | Next credential lifecycle event; gitignore already in place | No immediate blocker; accepted-risk |
| **OP-6** | F821 undefined-name review | Separate reviewed step per obkatka step2 spec | Post-merge / Q3 |

---

## 8. FINE-Pass Verdict

| Dimension | Verdict |
|-----------|---------|
| **Charter §8 (Tor/onion)** | ✅ CLOSED — roadmap purged + runtime guardrail enforces |
| **Network isolation (0.0.0.0)** | ✅ RESOLVED — design-safe (compose 127.0.0.1); vendored non-prod |
| **Secrets hygiene (S-18)** | ⚠️ ACCEPTED-RISK — gitignored + masked; rotation deferred to operator |
| **Quality gate / test harnesses** | ✅ CLOSED-ON-BRANCH — 524 pass, 43%, floor 35%, test step blocking |
| **Production-readiness gaps G-1..G-4** | ✅ CLOSED-ON-BRANCH — all 4 gaps have artifacts committed |
| **Merge to OpenManus main** | ⏳ PENDING-MERGE — operator action OP-1/OP-2 required |
| **Recon branch delivery to banxe main** | ⏳ PENDING-MERGE — operator action OP-3/OP-4 required |

**Overall: FINE-PASS COMPLETE. All factory actions done. Pending operator merge.**

The Legion engine, as of `feat/quality-gate-safe-port-20260714 @ b48852c`, satisfies all
Charter §8 compliance requirements and has addressed all G-1..G-4 production-readiness gaps.
The hardening is isolated to the branch and requires operator push + merge to land on `main`.

---

*BANXE Factory Agent | FINE pass | Reconciliation Worktree | 2026-07-15*
*Worktree: banxe-emi-stack-reconciliation-20260714 | Branch: feat/reconciliation-charter-20260714*
*Legion ref: feat/quality-gate-safe-port-20260714 @ b48852c | Banxe ref: origin/main @ 312ce3d*
*Charter §9 — no FCA logic ported. Charter §8 — no Tor/onion in any first-party code or roadmap.*
