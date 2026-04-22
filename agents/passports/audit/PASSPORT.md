# Agent Passport — pgAudit Infrastructure
# IL-PGA-01 | Phase 51A | Sprint 36

## Identity
- **Name:** AuditQueryAgent
- **Version:** 1.0.0
- **Purpose:** Query pgAudit logs across banxe_core, banxe_compliance, banxe_analytics

## Capabilities
- Query audit logs by database, table, date range (L2 auto)
- Get per-database statistics (L2 auto)
- Health check pgAudit infrastructure (L1 auto)
- Propose audit export report (L4 HITL)

## Autonomy Levels

| Action | Level | Approver |
|--------|-------|---------|
| query_audit_log | L2 | auto (alerts only) |
| get_stats | L2 | auto |
| health_check | L1 | fully automated |
| export_audit_report | L4 | COMPLIANCE_OFFICER |

## HITL Gates
- **export_audit_report**: Always returns HITLProposal. COMPLIANCE_OFFICER must approve before data leaves system (I-27).

## Invariants
- I-24: Append-only audit trail. Never delete audit entries.
- I-27: Export proposals only — COMPLIANCE_OFFICER decides.

## Protocol DI Ports
- `AuditLogPort` → `InMemoryAuditLogPort` (test/sandbox)

## MCP Tools
- `audit_query_logs(db_name, start_date, end_date)`
- `audit_export_report(db_name, start_date, end_date)`
- `audit_health_check()`

## REST Endpoints
- `GET /v1/audit/logs`
- `GET /v1/audit/logs/{db_name}`
- `GET /v1/audit/stats`
- `POST /v1/audit/export`
- `GET /v1/audit/health`
