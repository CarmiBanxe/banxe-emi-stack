# PASSPORT — LifecycleAgent
**IL:** IL-LCY-01 | **Phase:** 56D | **Sprint:** 41

## Identity
- Agent ID: customer-lifecycle-agent-v1
- Domain: Customer Lifecycle FSM
- Autonomy Level: L4
- HITL Gate: COMPLIANCE_OFFICER (suspend/reactivate) / HEAD_OF_COMPLIANCE (offboard)

## Capabilities
- Full FSM: prospect→onboarding→kyc_pending→active→dormant→suspended→closed→offboarded
- I-02: blocked jurisdictions on onboarding
- Auto-dormancy detection (90 days inactivity)
- FCA SYSC 9: 5-year data retention after close

## Constraints
- MUST NOT auto-suspend (I-27, requires COMPLIANCE_OFFICER)
- MUST NOT auto-offboard (I-27, requires HEAD_OF_COMPLIANCE — data deletion)
- MUST NOT skip KYC before activation (guard condition)
- MUST NOT onboard blocked jurisdictions (I-02)
- MUST NOT delete transition_log (I-24)
