# Agent Passport — FIN060 Regulatory Reporting
# IL-FIN060-01 | Phase 51C | Sprint 36

## Identity
- **Name:** ReportingAgent
- **Version:** 2.0.0
- **Purpose:** FIN060 regulatory report generation and approval

## Capabilities
- Generate monthly FIN060 report (L4 HITL)
- Retrieve FIN060 report by period (L1 auto)
- Get dashboard summary (L1 auto)
- Approve FIN060 report (L4 HITL)
- Submit to RegData — BT-006 stub (NotImplementedError)

## Autonomy Levels

| Action | Level | Approver |
|--------|-------|---------|
| get_report | L1 | fully automated |
| get_dashboard | L1 | fully automated |
| generate_fin060 | L4 | CFO |
| approve_report | L4 | CFO |
| submit_to_regdata | N/A | BT-006 not integrated |

## HITL Gates
- **generate_fin060**: Always returns HITLProposal. CFO must approve (I-27).
- **approve_report**: Always returns HITLProposal. CFO must confirm (I-27).

## Invariants
- I-01: All amounts Decimal, never float
- I-24: Append-only report store. No delete.
- I-27: Generate and approve propose only — CFO decides.

## Protocol DI Ports
- `ReportStorePort` → `InMemoryReportStore` (test/sandbox)

## MCP Tools
- `fin060_generate(month, year)`
- `fin060_get_report(month, year)`
- `fin060_approve(report_id)`
- `fin060_dashboard()`

## REST Endpoints
- `POST /v1/fin060/generate`
- `GET /v1/fin060/{year}/{month}`
- `GET /v1/fin060/history`
- `POST /v1/fin060/{report_id}/approve`
- `GET /v1/fin060/dashboard`

## BT-006 Stub
- `submit_to_regdata()` raises `NotImplementedError("BT-006: RegData API not integrated")`
- RegData integration tracked in backlog as BT-006
