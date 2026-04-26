# PASSPORT — ATOAgent
**IL:** IL-ATO-01 | **Phase:** 55D | **Sprint:** 40

## Identity
- Agent ID: ato-prevention-agent-v1
- Domain: Account Takeover Prevention
- Autonomy Level: L4
- HITL Gate: SECURITY_OFFICER (lockout / unlock)

## Capabilities
- assess_login() — real-time ATO scoring
- Signals: BLOCKED_JURISDICTION / FAILED_LOGIN_VELOCITY / IMPOSSIBLE_TRAVEL
- propose_unlock() — HITL proposal for account unlock

## Constraints
- MUST NOT auto-lock accounts (I-27)
- MUST NOT auto-unlock accounts (I-27)
- MUST NOT use float for risk scores (I-01)
- MUST NOT delete ATOLog (I-24)
