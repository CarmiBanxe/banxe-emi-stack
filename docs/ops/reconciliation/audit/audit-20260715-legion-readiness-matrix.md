# Legion (OpenManus) — Readiness Baseline Matrix
# STATUS: DRAFT — Legion code still evolving; re-run before production launch
# Audit date: 2026-07-15 | Repo: OpenManus-quality-gate-20260714 @ 4509a94
# Produced by: BANXE Factory Agent | PROP-2026-0714-001

---

## 1. Claim → Proof → Status Matrix

### 1.1 Streaming

| Claim | Evidence (file:artifact) | Status |
|-------|--------------------------|--------|
| SSE endpoint exists | `openmanus_rl/api/streaming.py`: `GET /v1/stream/generate` → `StreamingResponse(media_type="text/event-stream")` | **CONFIRMED** |
| WebSocket endpoint exists | `openmanus_rl/api/streaming.py`: `@app.websocket("/ws/stream")`; `agent_server.py:86` SSE path | **CONFIRMED** |
| Streaming has test coverage | `tests/integration/test_websocket_endpoint.py` (skipped when server absent — correct) | **CONFIRMED** |
| Formal event schema artifact | No JSON Schema / AsyncAPI / typed envelope for stream events found | **PARTIAL** |
| Live end-to-end demo verified | `streaming.py:22` inline JS WebSocket client exists; no recorded end-to-end run in CI or docs | **PARTIAL** |

### 1.2 Memory / RAG

| Claim | Evidence (file:artifact) | Status |
|-------|--------------------------|--------|
| SQLite memory schema | `openmanus_rl/memory/hermes_memory_integration.py`: `CREATE TABLE` for working / semantic / episodic / skills_memory; `sqlite3.connect`; `DEFAULT_DB_PATH = ~/.openmanus/hermes_memory.db` | **CONFIRMED** |
| Session-scoped persistence | `session_id` column present across memory tables; working memory is session-scoped | **CONFIRMED** |
| Retrieval / ranking path | Memory logic: 730 grep hits across codebase; extensive but no single isolated retrieval+ranking module identified | **PARTIAL** |
| Vector store (RAG) | `chroma` / `faiss` / `qdrant` = 0 hits; `embedding` referenced in 36 places but no vector-index artifact found — RAG appears keyword/SQL-based, not vector | **GAP** |

### 1.3 Eval / Readiness

| Claim | Evidence (file:artifact) | Status |
|-------|--------------------------|--------|
| Eval harness exists | `eval/` directory; `tests/test_eval_harness.py`; `tests/test_eval_suites.py`; dataset loaders (babyai / gaia / etc.) | **PARTIAL** |
| Golden reference set | No explicit golden-answer file or fixture set found; eval datasets are task sets, not reference outputs | **PARTIAL** |
| Regression thresholds | `satisficing_threshold`, `performance_validator THRESHOLDS`, `threshold` (53 hits) — these are decision/perf thresholds, not CI regression gates | **PARTIAL** |
| Blocking gate in CI / release | `quality-gate.yml`: all steps `continue-on-error: true`; `--cov-fail-under=20` advisory; gate is intentionally non-blocking (operator decision, targeting Q3) | **GAP** *(intentional)* |

### 1.4 Security / Ops

| Claim | Evidence (file:artifact) | Status |
|-------|--------------------------|--------|
| Secrets not hardcoded | `os.environ` / `os.getenv` used throughout; `config.toml` gitignored; API key masked in logs | **PARTIAL** |
| Structured logging + metrics | `openmanus_rl/observability/`: `logging.py` (structlog), `health.py`, `MetricsCollector`; 57 tests green | **CONFIRMED** |
| Health endpoint | `openmanus_rl/api/health.py`; 5 health endpoint tests passing | **CONFIRMED** |
| Rollback / runbook artifact | `docs/NETWORK_HARDENING.md` present; no rollback runbook, no incident-response doc found | **GAP** |
| Budget / rate-limit controls | No token-budget cap, no per-client rate-limit, no cost-circuit-breaker found in codebase | **GAP** |

### 1.5 Core Architecture

| Claim | Evidence (file:artifact) | Status |
|-------|--------------------------|--------|
| LLM integration (litellm) | 230 hits; primary LLM abstraction layer; multi-provider routing functional | **CONFIRMED** |
| Tool framework | 288 hits; `openmanus_rl/tools/`; pluggable tool registry; tool-calling tested | **CONFIRMED** |
| Agent orchestration | 396 hits; `openmanus_rl/agents/`; multi-turn rollout; modular stage processor | **CONFIRMED** |
| FastAPI web layer | 41 hits; `agent_server.py` (:8090), health (:8080), streaming (:8081) — all bind `127.0.0.1` | **CONFIRMED** |
| No inadvertent 0.0.0.0 binds (first-party) | First-party servers bind `127.0.0.1`; `flask` / `typer` / `sqlalchemy` = 0 hits (clean architecture) | **CONFIRMED** |
| verl / webshop 0.0.0.0 binds | Upstream verl trainer and webshop demo may bind `0.0.0.0` — pending non-prod confirmation; not first-party code | **PARTIAL** |

---

## 2. Test Suite Baseline (2026-07-15 @ 4509a94)

| Metric | Value |
|--------|-------|
| First-party test files | 53 |
| Passed | 488 |
| Skipped (env-gated) | 5 |
| Failed | 0 |
| Coverage (`openmanus_rl/`) | 42% |
| Coverage floor (advisory) | 20% |
| CI gate mode | Advisory (`continue-on-error: true`) |

---

## 3. Consolidated GAP List

| # | Gap | Risk | Owner / Target |
|---|-----|------|---------------|
| G-1 | **Vector-store RAG absent** — embeddings referenced but no chroma/faiss/qdrant; retrieval is keyword/SQL | Semantic recall quality limited for long-context memory tasks | Product / Q3 |
| G-2 | **Blocking eval gate absent** — CI is advisory; no pass/fail threshold for regression coverage | Regressions can merge silently | Infra / Q3 (operator-accepted until then) |
| G-3 | **Rollback / runbook missing** — no documented incident-response or deployment rollback procedure | Production incident MTTR undefined | Ops / pre-launch |
| G-4 | **Budget / rate-limit absent** — no token-budget cap, no per-client rate-limit, no cost circuit-breaker | Runaway LLM cost in production; no blast-radius limit | Platform / pre-launch |

### 3.1 Carried-Forward Operator Notes

| Note | Detail | Status |
|------|--------|--------|
| S-18 key rotation | B1 gateway key rotation skipped — operator-accepted risk; keys not changed during obkatka | SKIPPED (accepted) |
| verl / webshop 0.0.0.0 | Upstream binds pending confirmation they are non-prod / test-only contexts | OPEN — awaiting operator confirmation |

---

## 4. Readiness Verdict

**Legion engine is functionally rich and test-green.**

The core stack (LLM via litellm, tool framework, agent orchestration, FastAPI, SQLite memory, structured
observability) is implemented and passing 488 tests with 42% coverage. Streaming endpoints (SSE + WebSocket)
exist and are tested. Security hygiene (no hardcoded secrets, `127.0.0.1` bind, gitignored config) is
adequate for a development/staging deployment.

**Four gaps must be closed before full production launch:**

1. Vector-store RAG (G-1) — functional gap in semantic retrieval quality
2. Blocking eval gate (G-2) — CI must gate on regression before production traffic
3. Rollback / runbook (G-3) — operational readiness prerequisite
4. Budget / rate-limit (G-4) — cost and blast-radius control

None of the gaps are blockers for continued development or staging use. All are blockers for production.

**Recommended next milestones (Q3 2026):**
- Harden CI gate: replace `continue-on-error: true` with hard failure on coverage regression
- Draft minimal runbook covering deploy / rollback / incident triage
- Add rate-limit middleware to `agent_server.py`

---

*BANXE Factory Agent | Reconciliation Worktree | 2026-07-15*
*Worktree: banxe-emi-stack-reconciliation-20260714 | Branch: feat/reconciliation-charter-20260714*
*Source: OpenManus-quality-gate-20260714 @ 4509a94 | Charter §9 — no FCA logic ported to Legion*
