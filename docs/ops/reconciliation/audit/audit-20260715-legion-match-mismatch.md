# Legion (OpenManus) — Match / Mismatch Reconciliation Report
# STATUS: FINAL | Audit date: 2026-07-15 | Charter §9 applies throughout
#
# Source A: /home/mmber/OpenManus/DEPLOYMENT_READY_ROADMAP.md (other-machine claim)
# Source B: audit-20260715-legion-readiness-matrix.md @ commit 201ce5b (live-code audit)
# Code ref:  OpenManus-quality-gate-20260714 @ 4509a94
# Produced by: BANXE Factory Agent | PROP-2026-0714-001

---

## 1. Headline Finding

**The roadmap (DEPLOYMENT_READY_ROADMAP.md) is STALE and UNDER-REPORTS readiness.**

The roadmap marks only **3 items `[x]` done** (memory module w/ Ollama, qwen2.5:7b params,
ALFWorld integration) and lists **87 `[ ]` TODO** items across 15 sprints. The live-code audit
(488 tests passing, 4509a94) proves that at least **4 roadmap-TODO items are already shipped**:
REST API on FastAPI, health checks, SSE/WebSocket streaming, and structured observability.

Legion is **more ready than its own roadmap claims**.

---

## 2. Mismatch Table — Roadmap Says TODO / Absent; Audit Says DONE

> VERDICT = MISMATCH (roadmap understates). Authoritative source: **live audit** (code is truth).

| # | Dimension | Roadmap Line / Status | Audit Status | Verdict |
|---|-----------|----------------------|--------------|---------|
| M-1 | REST API on FastAPI | Line 34, Sprint 2, `[ ]` TODO | **CONFIRMED** — `agent_server.py` (:8090), `server.py`, `health.py`, `streaming.py`; all FastAPI; all bind `127.0.0.1` | **MISMATCH** — roadmap understates |
| M-2 | Health checks | Line 102, Sprint 8, `[ ]` TODO | **CONFIRMED** — `openmanus_rl/api/health.py`; 5 integration tests pass | **MISMATCH** — roadmap understates |
| M-3 | SSE / WebSocket streaming | Not listed in any sprint TODO | **CONFIRMED** — `streaming.py`: `@app.websocket("/ws/stream")`, `GET /v1/stream/generate` → `StreamingResponse(text/event-stream)`; `agent_server.py:86` SSE | **MISMATCH** — roadmap absent; feature shipped |
| M-4 | Audit trail / structured logging | Line 136, Sprint 11, `[ ]` TODO | **CONFIRMED** — `openmanus_rl/observability/`: `logging.py` (structlog), `health.py`, `MetricsCollector`; 57 tests green | **MISMATCH** — roadmap understates |

**Summary: 4 MISMATCH items.** In all cases the live code is ahead of the roadmap's recorded state.

---

## 3. Match Table — Both Sources Agree: Not Yet Done

> VERDICT = MATCH (both flag as pending). Sprint intent from roadmap; gap evidence from audit.

| # | Dimension | Roadmap Line / Sprint | Audit Status | Verdict |
|---|-----------|----------------------|--------------|---------|
| A-1 | Vector DB / RAG (Qdrant) | Lines 80–81, Sprint 6, `[ ]`; Sprint 4 line 60 (RAG for docs) | **GAP G-1** — `chroma`/`faiss`/`qdrant` = 0 hits; embedding referenced but no vector-index artifact | **MATCH** — both agree: not done |
| A-2 | Automated evaluation pipelines | Line 127, Sprint 10, `[ ]` | **GAP G-2** — eval harness exists but CI gate is advisory (`continue-on-error: true`); no blocking regression threshold | **MATCH** — both agree: not done |
| A-3 | NeMo Guardrails | Line 133, Sprint 11, `[ ]` | Guardrail = 0 hits in first-party engine; guardrail is planned as external shim | **MATCH** — both agree: not done |
| A-4 | Backup / monitoring / auto-recovery | Lines 103–105, Sprint 8, `[ ]` | **GAP G-3** — no rollback runbook, no incident-response doc; `docs/NETWORK_HARDENING.md` exists but is not a runbook | **MATCH** — both agree: not done |
| A-5 | Budget / rate-limit / cost control | Not explicitly in roadmap | **GAP G-4** — no token-budget cap, no per-client rate-limit, no cost circuit-breaker | **MATCH** — both agree: not done |

**Summary: 5 MATCH items.** Sprint structure from roadmap is useful for planning; audit provides evidence.

---

## 4. *** CRITICAL COMPLIANCE FLAG — HIGH ***

### Tor / Onion References in Roadmap

The roadmap contains **6 references** to Tor network and onion-site integration:

| Line | Sprint / Section | Text (original) |
|------|-----------------|----------------|
| 61 | Sprint 4 (Search), `[ ]` | "Интеграция с onion-сайтами для Tor доступа" |
| 138 | Sprint 11 (Privacy & Security), `[ ]` | "Настройка Tor доступа для onion-сайтов" |
| 193 | Q2 2027 Future Direction | "Полная поддержка Tor сети" |
| 194 | Q2 2027 Future Direction | "Расширенный onion-поиск" |
| 214 | Technical Priorities section | "Enhanced Search: DuckDuckGo, Google, browser_use, **Tor**" |
| 224 | Key Deployment Patterns | "Privacy Options: Tor поддержка, onion-доступ" |

### Violation Assessment

**DIRECT VIOLATION of Charter §8 (immutable):** Legion→Banxe SAFE-PORT forbids porting or implementing
Tor / onion / anonymity-network capabilities. These roadmap items must be removed from the Legion
roadmap before any code is ported to Banxe or integrated into shared infrastructure.

**Current code status:** Prior manifest scan (2026-07-14) found 0 Tor/onion implementation in
`openmanus_rl/` first-party code. The risk is roadmap intent, not yet shipped code.

**Recommended action (OPERATOR-GATED — do NOT edit roadmap or code here):**
1. Operator to explicitly remove lines 61, 138 (active TODOs) and lines 193–194, 214, 224 from roadmap
2. Add `# FORBIDDEN: Tor/onion — Charter §8` annotation or delete the sections entirely
3. Confirm via grep scan before any Legion→Banxe integration step: `grep -r -i "tor\|onion" openmanus_rl/`

**Status: OPEN / HIGH / operator-decision required before next integration sprint.**

---

## 5. Convergence — Best of Both (Unified Authoritative Status)

For each dimension, the authoritative source is determined by which has better evidence:

| Dimension | Authoritative Source | Unified Status |
|-----------|---------------------|---------------|
| REST API, health, streaming, observability | **Live audit** (roadmap stale) | ✅ SHIPPED — treat as done in any planning doc |
| SQLite memory (working/semantic/episodic/skills, session_id) | **Live audit** (roadmap says "basic"; audit shows full schema) | ✅ SHIPPED — more capable than roadmap states |
| VERL integration, WebShop/ALFWorld/GAIA envs, Ollama | **Both agree** | ✅ SHIPPED |
| Vector DB / RAG, blocking eval gate, rollback/runbook, budget/rate-limit | **Both agree** | ❌ GAP — use roadmap sprint structure for planning |
| NeMo Guardrails | **Both agree** | ❌ GAP (Sprint 11 intent) |
| Tor / onion items | **Compliance gate overrides both** | 🚫 FORBIDDEN — Charter §8; remove from roadmap regardless of roadmap intent |

**Principle:** roadmap sprint structure is useful as *intent and sequencing*; live audit is authoritative
for *current state*. Any document claiming Legion's current status must use the audit as ground truth.

---

## 6. Unified Gap List — Path to Production

Deduplicated from both sources, ordered by risk:

| ID | Gap | Source | Risk | Target |
|----|-----|--------|------|--------|
| **COMPLIANCE** | Remove Tor/onion roadmap items (lines 61, 138, 193–194, 214, 224) | Compliance audit | **HIGH** — Charter §8 violation; blocks integration | Operator-gated, immediate |
| G-1 | Vector-store RAG (Qdrant / chroma / faiss absent) | Both | Semantic recall quality limited | Q3 2026 (Sprint 6) |
| G-2 | Blocking eval gate (CI advisory-only) | Both | Regressions can merge silently | Q3 2026 (Sprint 10) |
| G-3 | Rollback / runbook absent | Both | MTTR undefined for production incidents | Pre-launch (Sprint 8) |
| G-4 | Budget / rate-limit / cost circuit-breaker | Audit (roadmap silent) | Runaway LLM cost in production | Pre-launch |
| NOTE | S-18 key rotation | Carried forward | Operator-accepted risk; keys not rotated during obkatka | SKIPPED (accepted) |
| NOTE | verl / webshop 0.0.0.0 binds | Carried forward | Awaiting non-prod confirmation | OPEN — operator to confirm |

---

## 7. Verdict

| Dimension | Finding |
|-----------|---------|
| **Overall alignment** | PARTIAL AGREE — both agree on gaps; DISAGREE on completeness |
| **Roadmap accuracy** | STALE — understates delivered state by at least 4 shipped features |
| **Code quality** | 488 tests / 42% coverage / 0 failures / E722 clean in first-party — solid baseline |
| **Compliance** | ONE HIGH FLAG — Tor/onion in roadmap; 0 Tor/onion in first-party code (clean) |
| **Production readiness** | NOT YET — 4 ops gaps (G-1 to G-4) + compliance flag must close first |
| **Staging readiness** | YES — engine is functionally rich, test-green, 127.0.0.1-bound |

**Legion is more ready than its own roadmap claims.** The roadmap needs a state-sync pass to reflect
shipped features before Sprint 2–3 planning is done. The Tor/onion items must be removed (operator
action) before any Banxe integration work proceeds. Once G-1 to G-4 are resolved and the compliance
flag is cleared, Legion is on a credible path to a production launch.

---

*BANXE Factory Agent | Reconciliation Worktree | 2026-07-15*
*Worktree: banxe-emi-stack-reconciliation-20260714 | Branch: feat/reconciliation-charter-20260714*
*Sources: OpenManus @ 4509a94 + DEPLOYMENT_READY_ROADMAP.md (other-machine)*
*Charter §9 hard line: no FCA logic, no banking credentials ported to Legion — ever*
