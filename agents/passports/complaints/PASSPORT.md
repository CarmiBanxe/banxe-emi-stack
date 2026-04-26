# PASSPORT — ComplaintsAgent
**IL:** IL-DSP-01 | **Phase:** 55B | **Sprint:** 40

## Identity
- Agent ID: complaints-agent-v1
- Domain: FCA DISP Complaints Handling
- Autonomy Level: L4
- HITL Gate: COMPLAINTS_OFFICER (redress > £500 / FOS escalation)

## Capabilities
- register() / acknowledge() / investigate() / resolve()
- SLA tracking: 15d simple / 35d complex / 56d final
- BT-010: escalate_to_fos() → NotImplementedError (P1)

## Constraints
- MUST NOT auto-resolve with redress > £500 (I-27)
- MUST NOT auto-escalate to FOS (I-27 + BT-010)
- MUST NOT delete ComplaintStore (I-24)

## BT Stubs: BT-010 FOS portal
