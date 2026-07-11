---
il_ts: 2026-07-11T00:04:00Z
session_id: banking-engine-b0b1-sandbox
source: factory
status: DONE (scaffold written — operator worktree setup + commit pending per I-71)
---

### B-0/B-1: Banking Engine (Banksy) — Sandbox Declaration + LangGraph Scaffold

- **Scope:** Sprint B-0 sandbox declaration + Sprint B-1 LangGraph scaffold.
  SANDBOX ONLY. No live banking connections. Execution host: evo1 (100.68.102.48).
  Legion thin-client only (ADR-103 DLP boundary enforced).

- **Artifacts written (staging area — NOT committed, I-71):**
  - `docs/ops/banking-engine/B0-SANDBOX-DECLARATION.md`
    → Sandbox mode table, backend config, DLP boundary (ADR-103), open items (OI-1/OI-8/OI-evo1-api/OI-budget),
      compliance gates (I-27/I-24/HITL), exit criteria for B-0.
  - `docs/ops/banking-engine/B1-LANGGRAPH-RUNBOOK.md`
    → Phase 1: venv + `pip install langgraph langchain-openai langgraph-checkpoint-sqlite httpx` on evo1.
      Phase 2: env vars (LITELLM_BASE_URL / LITELLM_API_KEY / LITELLM_MODEL), BudgetManager sandbox cap,
      SqliteSaver config. Phase 3: smoke test commands. Phase 4: done criteria checklist.
  - `services/banking-engine/graph_sandbox.py`
    → Async LangGraph `StateGraph[BankingState]` (1 node), START → banking_node → END.
      LiteLLM :4000 alias `banxe-general` via ChatOpenAI. SqliteSaver checkpointer (in-memory default).
      LITELLM_API_KEY via `os.environ["LITELLM_API_KEY"]` — fails fast if unset.
      No banking tools wired. I-27 annotated in node docstring.

- **Backend confirmed:**
  - LiteLLM :4000 HTTP 200 audited 2026-07-11. `banxe-general` alias confirmed in 20-alias list.
  - banxe-general → qwen3:30b-a3b on evo2/evo1 (OI-LOCAL-1 G-1 resolution).

- **Security invariants:**
  - No credentials hardcoded. No PII, IBAN, banking endpoints in any file.
  - LITELLM_API_KEY = env var only (fails fast with KeyError if unset — correct by design).
  - Scaffold imports: langchain-openai + langgraph only. No banking adapters/MCP imports.

- **Operator action required (I-71 — operator commits, factory NEVER pushes):**
  1. Move staging to tmp:
     `mv ~/wt/banking-engine-b0b1 /tmp/banksy-staging`
  2. Create git worktree:
     `cd ~/banxe-emi-stack && git fetch origin main && \
      git worktree add ~/wt/banking-engine-b0b1 \
        -b agent/factory/bankingengine/b0b1-sandbox origin/main`
  3. Copy scaffold into worktree:
     `cp -r /tmp/banksy-staging/docs /tmp/banksy-staging/services \
            /tmp/banksy-staging/ledger ~/wt/banking-engine-b0b1/ && \
      rm -rf /tmp/banksy-staging`
  4. Review B0-SANDBOX-DECLARATION.md (acknowledge scope)
  5. Install packages on evo1: `pip install langgraph langchain-openai langgraph-checkpoint-sqlite httpx`
  6. Run smoke test on evo1: `LITELLM_API_KEY=sk-banxe-llm-gateway-2026 python services/banking-engine/graph_sandbox.py`
  7. When smoke test passes: `git add docs/ services/ ledger/ && git commit && git push`
  8. Report B-1 done to factory → factory writes B-1 close ledger event.

- **Compliance:**
  - BDSL thresholds NOT set. Requires MLRO/CRO approval before any live financial data flows.
  - EU AI Act Art.14 / I-27: agent L2 autonomy only; L3+ requires human approval.
  - ADR-103: no banking credentials on Legion or in Private Engine config.

- **Append-only (ADR-059-A):**
  il_ts 2026-07-11T00:04:00Z strictly > 2026-07-11T00:03:00Z (T1c llama-server event).

- **Next sprint (B-2):** multi-node graph + tool stubs + ADR-008 (LangGraph vs Temporal).

- **Refs:**
  `docs/ops/banking-engine/B0-SANDBOX-DECLARATION.md`,
  `docs/ops/banking-engine/B1-LANGGRAPH-RUNBOOK.md`,
  `services/banking-engine/graph_sandbox.py`,
  `SESSION-STATE.md` (private-engine-openmanus worktree — T3 track added),
  ADR-103, agent-authority.md, security-policy.md.
