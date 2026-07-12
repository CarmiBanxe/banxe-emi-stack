# B0 Sandbox Declaration — Banking Engine (Banksy)
# Sprint: B-0 | Status: SANDBOX ONLY — no live banking connections
# Created: 2026-07-11 | Source: factory artifact (I-71 — operator commit required)
# Branch: agent/factory/bankingengine/b0b1-sandbox

---

## 1. SANDBOX MODE

**ALL external banking calls are stubs or mocks in this sprint. No live connections.**

| System | B-0 status | Production target |
|--------|------------|-------------------|
| PSD2 / Adorsys | MOCK — not wired | Real CAMT.053 polling (Sprint B-5+) |
| MCP banking tools | STUB — not wired | Live tools on evo1 (Sprint B-3+) |
| Midaz ledger | MOCK — not wired | `create_tx()` / `get_balance()` (Sprint B-4+) |
| LangGraph nodes | 1-node scaffold | Full multi-node graph (Sprint B-2+) |
| Keycloak IAM | Running :8180 → 302 | JWT validation wired in B-3 |
| PostgreSQL | Not connected | Schema + Alembic migrations in B-4 |

This sandbox produces NO financial outputs. All results are mock/test data only.

---

## 2. BACKEND CONFIGURATION

| Parameter | Value | Status |
|-----------|-------|--------|
| LLM gateway | LiteLLM :4000 | HTTP 200 — audited 2026-07-11 |
| Default model alias | `banxe-general` | Confirmed in litellm-config.v2.yaml (audited) |
| Execution host | evo1 (100.68.102.48:11434) | UP — audited 2026-07-11 |
| Failover host | evo2 (192.168.0.15:11434) | UP — audited 2026-07-11 |
| API key | `$LITELLM_API_KEY` (env var) | Never hardcoded — security-policy.md |
| IPv4 only | `127.0.0.1:4000` | `::1:4000` refused (IPv6 off) |
| Orchestrator | LangGraph | Correction 7 / S-18 line 63; OI-8 LangGraph-first |

---

## 3. BOUNDARY — LEGION vs EVO (ADR-103 / Correction 1)

**Legion (local machine) = THIN CLIENT ONLY.**

- Legion MUST NOT execute banking logic or graph nodes.
- Legion has NO write path to the banking ledger.
- All LangGraph execution runs on **evo1**; evo2 is failover.
- DLP hard rule: no banking credentials, Postgres passwords, customer PII, IBANs, or
  banking source code may cross to the Legion environment or Private Engine (OpenManus).
- `banxe-general` alias is **BANNED from Private Engine config.toml** (reserved for Banking Engine).
- MCP banking tools invoked from evo1 only — never directly from Legion.

---

## 4. OPEN ITEMS

| ID | Item | Status | Resolution path |
|----|------|--------|----------------|
| OI-1 | Default banking alias | `banxe-general` PROPOSED — config-audit pending | MLRO/CRO sign-off before live use |
| OI-8 | Temporal vs LangGraph | LangGraph-first (Correction 7; S-18 line 63) | ADR-008 in Sprint B-2 |
| OI-evo1-api | evo1 :8090/health → 404 | UNKNOWN — wrong endpoint or API not active | Infra team verification required |
| OI-budget | LiteLLM BudgetManager per-agent cap | NOT SET | Runbook §2.2; requires gateway owner approval |

---

## 5. COMPLIANCE / HITL GATES

BDSL thresholds: **NOT SET**. Requires MLRO/CRO approval before any real financial data
flows through LangGraph.

| Gate | Timeout | Required roles | Escalation |
|------|---------|---------------|-----------|
| SAR filing | 24 h | MLRO | → CEO |
| AML threshold change | 4 h | MLRO + CEO | — |
| Sanctions reversal | 1 h | MLRO + CEO | — |
| PEP onboarding | 48 h | MLRO | — |

- **EU AI Act Art.14:** Human oversight required for all L3+ agent decisions.
- **I-27:** Agents PROPOSE only — never auto-apply financial decisions.
- **I-24:** All state transitions must log to append-only audit when wired in B-3+.
- **POCA 2002 s.330:** SAR candidates always escalate to MLRO (L4).
- Full autonomy matrix: `docs/ops/banking-engine/COMPLIANCE-GATES.md`.

---

## 6. EXIT CRITERIA — B-0 COMPLETE WHEN

- [ ] This declaration acknowledged by operator (read + noted)
- [ ] B-1 runbook executed on evo1 (1-node graph round-trip confirmed)
- [ ] Reply from `banxe-general` is a non-empty string
- [ ] Checkpoint row persisted (SqliteSaver thread verified)
- [ ] No live banking API calls made (audit: grep for Adorsys/PSD2/IBAN → expect zero)
- [ ] Operator reports B-0 done → factory writes B-1 ledger-close event

---

## References

- Runbook: `docs/ops/banking-engine/B1-LANGGRAPH-RUNBOOK.md`
- Compliance gates: `docs/ops/banking-engine/COMPLIANCE-GATES.md`
- Graph scaffold: `services/banking-engine/graph_sandbox.py`
- ADR-103 DLP: `docs/adr/ADR-103-dlp-boundary.md`
- Agent authority: `.claude/rules/agent-authority.md`
- Security policy: `.claude/rules/security-policy.md`
