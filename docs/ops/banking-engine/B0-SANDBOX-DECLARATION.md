# B0 Sandbox Declaration — Banking Engine (Banksy)
# Sprint: B-0 | Status: SANDBOX ONLY — no live banking connections
# Created: 2026-07-11 | Source: factory artifact (I-71 — operator commit required)
# Branch: agent/factory/bankingengine/b0b1-sandbox

---

## 1. SANDBOX MODE

ALL external banking calls are stubs or mocks in this sprint. No live connections to any
PSD2 gateway, bank, MCP banking tool, or ledger. All outputs are test/mock data only.

| System | Status in B-0 sandbox | Production target |
|--------|----------------------|-------------------|
| PSD2 / Adorsys | MOCK — not wired | Real CAMT.053 polling (Sprint B-5+) |
| MCP banking tools | STUB — not wired | Live tools on evo1 (Sprint B-3+) |
| Midaz ledger | MOCK — not wired | `create_tx()` / `get_balance()` (Sprint B-4+) |
| LangGraph nodes | Scaffold only — 1-node graph | Full multi-node graph (Sprint B-2+) |
| Keycloak IAM | Running on :8180 (→ 302 redirect) | JWT validation in B-3 |
| PostgreSQL | Not connected | Schema migrations in B-4 |

---

## 2. BACKEND CONFIGURATION

| Parameter | Value | Confirmed |
|-----------|-------|-----------|
| LLM gateway | LiteLLM :4000 | HTTP 200 audited 2026-07-11 |
| Default model alias | banxe-general | Confirmed in litellm-config.v2.yaml |
| banxe-general backend | qwen3:30b-a3b on evo2 / evo1 | Confirmed from 20-alias audit |
| Execution host | evo1 (100.68.102.48) | UP — audited 2026-07-11 |
| Failover host | evo2 (192.168.0.15) | UP — audited 2026-07-11 |
| API key | $LITELLM_API_KEY (env var) | Never hardcoded — security-policy.md |
| IPv4 only | 127.0.0.1:4000 | NOT ::1:4000 — IPv6 refused |

---

## 3. BOUNDARY — LEGION vs EVO (ADR-103 / Correction 1)

**Legion (local machine) = THIN CLIENT ONLY.**

- Legion MUST NOT execute banking logic.
- Legion has NO write path to the banking ledger.
- All LangGraph graph execution runs on evo1; evo2 is failover.
- DLP hard rule (ADR-103): no banking credentials, Postgres passwords, customer PII,
  IBANs, or banking source code in Legion config or Private Engine (OpenManus) context.
- `banxe-general` alias is BANNED from Private Engine config.toml (I-71 enforcement target).
- MCP banking tools are invoked from evo1 only — never directly from Legion.

---

## 4. OPEN ITEMS

| ID | Item | Status | Resolution path |
|----|------|--------|----------------|
| OI-1 | Default banking alias confirmed | banxe-general PROPOSED | Config audit complete; pending MLRO/CRO sign-off before live use |
| OI-8 | Temporal vs LangGraph ADR | LangGraph-first (Correction 7) | ADR-008 to be written in Sprint B-2 |
| OI-evo1-api | evo1 :8090/health returns 404 | UNKNOWN — wrong endpoint or API down | Infra team verification required |
| OI-budget | LiteLLM BudgetManager per-agent cap | NOT SET | B-1 runbook §2.2 proposes sandbox cap; requires gateway owner approval |

---

## 5. COMPLIANCE / HITL

- All L3+ agent actions require human approval (EU AI Act Art.14 / agent-authority.md).
- I-27 (HITL): this engine PROPOSES, never auto-applies financial decisions.
- BDSL thresholds: NOT SET. MLRO/CRO approval required before any real financial data
  flows through LangGraph.
- SAR candidates: L4 escalation to MLRO always (POCA 2002 s.330).
- I-24: all state transitions will log to append-only audit when wired in B-3+.
- This sandbox produces NO financial outputs. All results are mock/test data only.

---

## 6. EXIT CRITERIA — B-0 COMPLETE WHEN

- [ ] This declaration acknowledged by operator (read and noted)
- [ ] B-1 runbook executed successfully (1-node graph round-trip confirmed on evo1)
- [ ] Reply received from banxe-general (non-empty string)
- [ ] Checkpoint present (SqliteSaver thread confirmed)
- [ ] No live banking API calls made (audit: grep logs for Adorsys/PSD2/IBAN URLs — expect zero)
- [ ] Operator reports B-0 done → factory writes B-0 ledger-close event

---

## References

- Runbook: `docs/ops/banking-engine/B1-LANGGRAPH-RUNBOOK.md`
- Graph scaffold: `services/banking-engine/graph_sandbox.py`
- ADR-103 DLP: `docs/adr/ADR-103-dlp-boundary.md`
- Agent authority: `.claude/rules/agent-authority.md`
- Security policy: `.claude/rules/security-policy.md`
- LiteLLM config: `litellm-config.v2.yaml` (gateway host)
- SESSION-STATE: `/home/mmber/wt/private-engine-openmanus/docs/governance/SESSION-STATE.md`
