# Audit Trail Agent Passport
## IL-AES-01 | Phase 40 | banxe-emi-stack

| Field | Value |
|-------|-------|
| Agent ID | audit-trail-agent-v1 |
| IL | IL-AES-01 |
| Phase | 40 |
| Trust Zone | RED |
| Autonomy Level | L1/L4 |
| FCA Refs | FCA SYSC 9, MLR 2017, GDPR Art.5(1)(f) |

## Capabilities

- Append audit events with SHA-256 chain hash (L1)
- Search and filter audit events (L1)
- Replay entity event history (L1)
- Reconstruct point-in-time state (L1)
- Integrity verification of event chains (L1)
- Retention policy management (list only, L1)
- Schedule purge proposals (L4 HITL — irreversible)

## HITL Gates

| Action | Gate | Approver |
|--------|------|---------|
| purge_audit_records | L4 — ALWAYS HITL | MLRO |

## Invariants

- I-12: SHA-256 chain hash on every event
- I-24: Append-only — no update/delete
- I-27: Purge is always HITL-gated
- I-08: Minimum 5-year retention (FCA)
