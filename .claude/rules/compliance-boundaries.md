# Compliance Domain Boundaries — BANXE AI BANK
# Source: CLAUDE.md, agents/compliance/swarm.yaml, 01-safety-orchestration.md
# Created: 2026-04-10
# Migration Phase: 3
# Purpose: Enforce strict domain separation for compliance-critical code

## Domain Separation Rule

The following domains MUST remain separate and MUST NEVER be merged:

1. **Banking Core** — `services/ledger/`, `services/payment/`, `services/customer/`, `services/agreement/`, `services/statements/`
2. **Compliance / AML / KYC** — `services/aml/`, `services/kyc/`, `services/fraud/`, `services/case_management/`, `services/resolution/`
3. **Transaction Monitoring** — `services/aml/tx_monitor.py`, `agents/compliance/soul/tm_agent.soul.md`
4. **Reconciliation** — `services/recon/`
5. **Reporting (FCA)** — `services/reporting/`, `dbt/`
6. **Shared Infrastructure** — `services/config/`, `services/events/`, `services/providers/`, `services/iam/`, `services/auth/`
7. **AI Agents / Orchestration** — `agents/compliance/`, `.claude/agents/`, `services/hitl/`
8. **Consumer Duty** — `services/consumer_duty/`, `services/complaints/`
9. **Future UI/UX** — web + mobile (not yet in this repo)

## Trust Zones

All compliance agents operate in **Trust Zone: RED** (highest sensitivity).

| Autonomy Level | Meaning | Examples |
|---------------|---------|----------|
| L1 Auto | Fully automated, no human review | Fetch balance, parse statement, log event |
| L2 Alert → Human | AI acts but alerts human for review | DISCREPANCY detected, SAR candidate |
| L3 Auto + HITL gate | AI auto-processes but blocked at gates | AML screening, sanctions check, fraud scoring |
| L4 Human Only | Only humans can act | SAR filing, FIN060 sign-off, threshold changes |

## FCA Regulatory References

- FCA CASS 15 (Safeguarding)
- MLR 2017 (AML/KYC)
- PSR 2017 / PSR APP 2024 (Payments)
- EU AI Act Art.14 (Human oversight of AI)
- POCA 2002 s.330 (SAR filing)
- PS22/9 (Consumer Duty)

## References

- Agent authority: `agents/compliance/swarm.yaml`
- HITL gates: `services/hitl/hitl_service.py`
- Domain map: `.ai/registries/domain-map.md`
