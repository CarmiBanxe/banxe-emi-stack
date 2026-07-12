# Compliance Gates — Banking Engine (Banksy)
# Created: 2026-07-11 | Sprint: B-0
# Source: agent-authority.md, CLAUDE.md §I-27, EU AI Act Art.14, POCA 2002 s.330
# Branch: agent/factory/bankingengine/b0b1-sandbox

## Invariant I-27 — Agents PROPOSE, Never Auto-Apply

All Banking Engine agents operate under **I-27**: they propose actions; a human
(MLRO, CFO, Compliance Officer, or CEO) makes the final decision.
No agent may autonomously execute an L3+ action. This is a hard invariant —
no sprint milestone or deadline overrides it.

---

## Autonomy Levels

| Level | Name | What the agent may do |
|-------|------|-----------------------|
| **L1** | Auto | Fully automated, no human review needed. Example: fetch balance, parse statement, log event. |
| **L2** | Alert → Human | Agent acts and alerts a human; human reviews asynchronously. Example: flag discrepancy, surface SAR candidate. |
| **L3** | Auto + HITL Gate | Agent processes automatically but is **blocked** at defined gates pending human approval. Example: AML screening, sanctions check, fraud scoring. |
| **L4** | Human Only | No AI action permitted. Only an authorised human may execute. Example: SAR filing, FIN060 sign-off, threshold changes. |

Default posture: err towards **L2 over L1**. Never assume L1 if L2 is feasible.

---

## HITL Gates — Banking Engine

| Gate | Required roles | Timeout | Escalation |
|------|---------------|---------|-----------|
| `SAR_filing` | MLRO | 24 h | → CEO |
| `AML_threshold_change` | MLRO + CEO | 4 h | — |
| `sanctions_reversal` | MLRO + CEO | 1 h | — |
| `PEP_onboarding` | MLRO | 48 h | — |
| `board_report_sign_off` | MLRO + BOARD | 3 days | — |

On timeout: escalate to the role in the **Escalation** column.
Timeouts are business-hours where noted in the FCA calendar.

---

## Compliance Agents — Autonomy Assignment

| Agent | Autonomy | Human double-check | HITL gates |
|-------|----------|--------------------|-----------|
| MLRO Agent (coordinator) | L2 | MLRO | SAR_filing, AML_threshold_change, sanctions_reversal, PEP_onboarding, board_report_sign_off |
| Sanctions Check Agent | L3 | MLRO | block ≥ 0.80 confidence; review ≥ 0.60 |
| AML / TM Agent | L3 | Compliance Officer | EDD thresholds: £10 k individual / £50 k corporate |
| Fraud Detection Agent | L3 | Fraud Analyst | Fraud score via adapter |
| CDD Review Agent | L2 | Compliance Officer | — |
| Reconciliation Agent | L1 (match) / L2 (discrepancy) | MLRO | L4 for resolution of confirmed gap |
| Reporting Agent (FIN060) | L1 (generate) / L2 (CFO review) | CFO | L4 for final sign-off |

---

## Regulatory References

| Rule | Source | What it mandates |
|------|--------|-----------------|
| I-27 | CLAUDE.md / invariant registry | Agents propose; human decides. No autonomous L3+ action. |
| EU AI Act Art.14 | Regulation (EU) 2024/1689 | Meaningful human oversight for all high-risk AI outputs. |
| POCA 2002 s.330 | Proceeds of Crime Act | SAR filing is an L4 human-only action; 24 h SLA. |
| MLR 2017 | Money Laundering Regulations | EDD triggers; AML/CDD obligations. |
| FCA CASS 15 | PS25/12 | Safeguarding reconciliation; daily cycle. |

---

## BDSL Thresholds (Banking Engine)

**NOT SET in B-0 sandbox.** All BDSL decision thresholds require MLRO/CRO approval
before any live financial data flows through LangGraph nodes.
Setting thresholds is an L4 action (MLRO + CRO co-sign).

---

## References

- Sandbox declaration: `docs/ops/banking-engine/B0-SANDBOX-DECLARATION.md`
- Agent authority matrix: `.claude/rules/agent-authority.md`
- HITL service: `services/hitl/hitl_service.py`
- AML thresholds: `services/aml/aml_thresholds.py`
- FCA compliance matrix: `banxe-architecture/docs/COMPLIANCE-MATRIX.md`
