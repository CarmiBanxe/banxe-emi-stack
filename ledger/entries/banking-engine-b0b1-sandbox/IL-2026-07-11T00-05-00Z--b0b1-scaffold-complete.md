---
il_ts: 2026-07-11T00:05:00Z
session_id: banking-engine-b0b1-sandbox
source: factory
status: DONE — 4 artifacts written; operator smoke-test + commit pending (I-71)
---

### B-0 / B-1: Banking Engine (Banksy) — Full Scaffold Complete

- **Scope:** Sprint B-0 sandbox declaration + B-1 LangGraph scaffold + compliance gates.
  SANDBOX ONLY. No live banking connections. No credentials/PII/IBAN in any file.
  Execution host: evo1 (100.68.102.48). Legion thin-client only (ADR-103).

- **Confirmed pre-flight state (audited 2026-07-11):**
  - LiteLLM :4000 `banxe-general` → HTTP 200.
  - evo1 + evo2 Ollama UP. Keycloak :8180 → 302. LangGraph NOT yet installed on evo1.
  - Orchestrator canon = LangGraph (Correction 7 / S-18 line 63; OI-8 LangGraph-first).

- **Artifacts written (NOT committed — I-71):**

  | File | Content |
  |------|---------|
  | `docs/ops/banking-engine/B0-SANDBOX-DECLARATION.md` | Sandbox mode table, backend config (LiteLLM :4000), DLP boundary (ADR-103), 4 open items, HITL gate table, exit criteria |
  | `docs/ops/banking-engine/B1-LANGGRAPH-RUNBOOK.md` | Phase 1–4: venv + pip install, env vars, BudgetManager cap location, SqliteSaver config, smoke test commands, done checklist |
  | `services/banking-engine/graph_sandbox.py` | Async `StateGraph[BankingState]` 1 node (START → banking_node → END); `ChatOpenAI` → LiteLLM :4000 `banxe-general`; SqliteSaver checkpointer; LITELLM_API_KEY from `os.environ` (fails fast); I-27 + EU AI Act Art.14 annotated in node docstring |
  | `docs/ops/banking-engine/COMPLIANCE-GATES.md` | L1–L4 autonomy table, 5 HITL gates (SAR 24h / AML 4h / sanctions 1h / PEP 48h / board 3d), compliance agents matrix, regulatory refs (I-27 / EU AI Act Art.14 / POCA 2002 s.330 / MLR 2017 / FCA CASS 15), BDSL thresholds NOT SET note |

- **Security invariants confirmed:**
  - No credentials hardcoded anywhere. `LITELLM_API_KEY = os.environ["LITELLM_API_KEY"]` — KeyError if unset.
  - No PII, IBAN, Swift codes, banking endpoints in any file.
  - No uncensored/abliterated model references (grep count = 0).
  - Scaffold imports: `langchain-openai` + `langgraph` only. No banking adapters, no MCP imports.

- **Operator action required (I-71 — operator commits; factory NEVER pushes):**
  1. Review all 4 files.
  2. On evo1: `pip install langgraph langchain-openai langgraph-checkpoint-sqlite httpx`
  3. On evo1: `export LITELLM_API_KEY=... && python services/banking-engine/graph_sandbox.py`
  4. Verify: non-empty reply + "Checkpoint: persisted" line.
  5. `git add docs/ops/banking-engine/ services/banking-engine/ ledger/ && git commit && git push`
  6. Report B-1 done → factory writes B-1 ledger-close event.

- **Next sprint (B-2):** Multi-node graph + tool stubs + ADR-008 (LangGraph vs Temporal decision).

- **Append-only (ADR-059-A):**
  il_ts 2026-07-11T00:05:00Z strictly > 2026-07-11T00:04:00Z (prev event).

- **Refs:**
  `docs/ops/banking-engine/B0-SANDBOX-DECLARATION.md`,
  `docs/ops/banking-engine/B1-LANGGRAPH-RUNBOOK.md`,
  `docs/ops/banking-engine/COMPLIANCE-GATES.md`,
  `services/banking-engine/graph_sandbox.py`,
  ADR-103, agent-authority.md, security-policy.md, I-27, I-24.
