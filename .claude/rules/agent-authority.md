# Agent Authority Matrix — BANXE AI BANK
# Source: .claude/agents/*.md, agents/compliance/swarm.yaml
# Created: 2026-04-10
# Migration Phase: 3
# Purpose: Define AI agent autonomy levels and HITL gates

## Autonomy Levels

| Level | Name | Description |
|-------|------|-------------|
| L1 | Auto | Fully automated, no human review needed |
| L2 | Alert → Human | AI acts but alerts human; human reviews |
| L3 | Auto + HITL Gate | AI processes automatically but blocked at defined gates |
| L4 | Human Only | Only authorized humans can perform the action |

## Compliance Swarm Agents (Trust Zone: RED)

| Agent | Autonomy | Human Double | HITL Gates |
|-------|----------|-------------|------------|
| MLRO Agent (coordinator) | L2 | MLRO | SAR_filing, AML_threshold_change, sanctions_reversal, PEP_onboarding, board_report_sign_off |
| Jube Adapter Agent | L3 | CTIO | — |
| Sanctions Check Agent | L3 | MLRO | block ≥ 0.80, review ≥ 0.60 |
| AML Check Agent | L3 | Compliance Officer | EDD thresholds: £10k individual / £50k corporate |
| TM Agent | L3 | Compliance Officer | Alert SLA: 2 seconds |
| CDD Review Agent | L2 | Compliance Officer | — |
| Fraud Detection Agent | L3 | Fraud Analyst | Fraud scoring via adapter |

## Operational Agents (.claude/agents/)

| Agent | Purpose | Authority |
|-------|---------|-----------|
| Reconciliation Agent | Daily safeguarding recon (CASS 7.15) | L1 auto for matching; L2 alert for discrepancy; L4 MLRO for resolution |
| Reporting Agent | Monthly FIN060 generation | L1 auto for generation; L2 CFO review for upload; L4 CFO for signing |

## HITL Gate Timeouts

| Gate | Required Roles | Timeout | Escalate To |
|------|---------------|---------|-------------|
| SAR_filing | MLRO | 24h | CEO |
| AML_threshold_change | MLRO, CEO | 4h | — |
| sanctions_reversal | MLRO, CEO | 1h | — |
| PEP_onboarding | MLRO | 48h | — |
| board_report_sign_off | MLRO, BOARD | 3 days | — |

## References

- Compliance swarm: `agents/compliance/swarm.yaml`
- Soul files: `agents/compliance/soul/`
- HITL service: `services/hitl/hitl_service.py`
- Operational agents: `.claude/agents/`
