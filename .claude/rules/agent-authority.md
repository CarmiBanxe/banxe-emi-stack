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


## Adverse-Media Intelligence Agent (Trust Zone: RED) — added 2026-07-27, hierarchy corrected

| Agent | Autonomy | Human Double | HITL Gates |
|-------|----------|-------------|------------|
| Adverse-Media Feed Agent (X / RSS / Web / OpenSanctions via CompositeFeed) | L2 (research prep) | Compliance Officer | dossier -> mandatory MLRO EDD decision |

### Chain of command (two-stage: research below, judgment above)
PRINCIPLE (SMCR): the MLRO must NOT command the search. Research is owned by the
compliance function (Compliance Officer); the MLRO receives an assembled dossier and DECIDES.
This keeps the SMF17 decision-maker from being investigator-and-judge of the same material.

- STAGE 1 — RESEARCH (owner: CDD Review Agent, human double: Compliance Officer):
  commands the CompositeFeed fetch via AdverseMediaService (feeds -> matcher -> hits) and
  assembles the DOSSIER (articles, composite score/confidence, subject identity, feed
  provenance, per-node SANDBOX/enablement state). L2, advisory, ZERO customer-state change.
- HANDOFF: the assembled dossier becomes the MLRO HITL case payload (existing enqueue point).
  Change vs before: the queue receives a DOSSIER, not bare hits. No customer-state change pre-enqueue.
- STAGE 2 — DECISION (owner: MLRO, L4, human, SMF17): reviews the dossier and decides.
  Unchanged gated path — no auto-clear, no auto-block.

### The feed agent OBEYS: AdverseMediaService, commanded by the CDD Review Agent (Stage 1).
### It does NOT report to MLRO directly for tasking; MLRO only receives the dossier and decides.

### Triggers (WHEN research starts)
1. ONBOARDING (reactive): should_screen() for risk_level in {MEDIUM,HIGH,VERY_HIGH,PROHIBITED}
   (I-04 EDD). Entry: api/routers/adverse_media.py -> screen_customer().
2. ONGOING MONITORING (proactive): services/compliance_automation/periodic_review.py scheduled
   re-screening. NOTE: adverse_media not yet wired into periodic_review — documented next step.

### Regulatory basis
MLR 2017 Reg.28 (EDD gathering = compliance function work); SYSC 6.3.9R (MLRO = oversight/
decision recipient); SMCR SMF17 (MLRO personal accountability -> decision independence).

### SANDBOX posture
X / RSS / Web nodes SANDBOX-off by default (env opt-in). PROD enablement requires
Compliance/MLRO sign-off + UK-GDPR lawful-basis assessment + ADR ratification.

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
