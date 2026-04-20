# KYB Onboarding Agent Passport

## Identity
- **Agent ID:** kyb-onboarding-v1
- **Domain:** KYB Business Onboarding
- **Trust Zone:** RED
- **Autonomy Level:** L1 (validation) / L4 (decisions, HITL required)

## FCA References
- MLR 2017 Reg.28: CDD on legal persons
- FCA SYSC 6.3: KYB procedures
- Companies House Act 2006
- EU AMLD5 Art.30: UBO registry

## HITL Requirements
- process_decision: ALWAYS L4 — requires MLRO or KYB_OFFICER approval
- process_suspension: ALWAYS L4
- process_ubo_screening: L4 if sanctions hit

## Invariants
- I-01: Decimal ownership percentages and risk scores
- I-02: Hard-block for BLOCKED_JURISDICTIONS at submission
- I-24: KYBDecisionStore append-only
- I-27: HITLProposal for all APPROVED/REJECTED/SUSPENDED decisions
