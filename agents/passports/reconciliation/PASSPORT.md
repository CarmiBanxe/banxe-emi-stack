# Agent Passport — Daily Safeguarding Reconciliation
# IL-REC-01 | Phase 51B | Sprint 36 | CASS 7.15

## Identity
- **Name:** ReconAgent
- **Version:** 2.0.0
- **Purpose:** Daily safeguarding reconciliation per CASS 7.15

## Capabilities
- Run daily CASS 7.15 reconciliation (L1/L2 auto)
- Detect discrepancies between ledger and bank statements (L1 auto)
- List breach reports (L1 auto)
- Propose breach resolution (L4 HITL)

## Autonomy Levels

| Action | Level | Approver |
|--------|-------|---------|
| run_daily (no breach) | L1 | fully automated |
| run_daily (breach <= £100) | L2 | alert, auto-records |
| run_daily (breach > £100) | L4 | COMPLIANCE_OFFICER |
| get_report | L1 | fully automated |
| list_breaches | L1 | fully automated |
| resolve_breach | L4 | COMPLIANCE_OFFICER |

## HITL Gates
- **Breach > £100 (BREACH_HITL_THRESHOLD)**: Returns HITLProposal. COMPLIANCE_OFFICER must approve resolution (I-27).

## Constants
- RECON_TOLERANCE_GBP = Decimal("0.01")
- BREACH_HITL_THRESHOLD = Decimal("100")

## Invariants
- I-01: All amounts Decimal, never float
- I-24: Append-only recon store. No delete.
- I-27: Breach resolution proposes only.

## Protocol DI Ports
- `ReconStorePort` → `InMemoryReconStore` (test/sandbox)

## MCP Tools
- `recon_run_daily(date_str)`
- `recon_get_report(date_str)`
- `recon_list_breaches()`

## REST Endpoints
- `POST /v1/safeguarding-recon/run`
- `GET /v1/safeguarding-recon/reports`
- `GET /v1/safeguarding-recon/reports/{recon_date}`
- `GET /v1/safeguarding-recon/breaches`
- `POST /v1/safeguarding-recon/breaches/{report_id}/resolve`
