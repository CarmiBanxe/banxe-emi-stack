# Preferences Agent Passport
## IL-UPS-01 | Phase 39 | banxe-emi-stack

| Field | Value |
|-------|-------|
| Agent ID | preferences-agent-v1 |
| IL | IL-UPS-01 |
| Phase | 39 |
| Trust Zone | AMBER |
| Autonomy Level | L1/L4 |
| FCA Refs | GDPR Art.7, Art.17, Art.20 |

## Capabilities

- Get/set/reset user preferences (L1 auto)
- Manage GDPR consent records (grant L1, withdraw L4 HITL)
- GDPR data export (L1 auto, SHA-256 I-12)
- GDPR data erasure requests (L4 HITL I-27)
- Notification preferences and quiet hours
- Locale settings and language fallbacks

## HITL Gates

| Action | Gate | Approver |
|--------|------|---------|
| consent_withdrawal | L4 — HITL required | DPO |
| data_erasure | L4 — HITL required | DPO |

## Invariants

- I-01: No float for money in format_amount
- I-12: SHA-256 on all data exports
- I-24: All changes audit-logged
- I-27: Consent withdrawal and erasure are HITL-gated
