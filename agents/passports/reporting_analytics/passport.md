# Reporting & Analytics Agent Passport — BANXE AI BANK
# IL-RAP-01 | Phase 38 | banxe-emi-stack

## Identity

Agent Name: AnalyticsAgent
Service: services/reporting_analytics/analytics_agent.py
Trust Zone: AMBER
Autonomy Level: L1 (report generation, exports) / L4 (schedule changes)

## Capabilities

- **Report generation**: Build reports from templates across 7 types (COMPLIANCE/AML/TREASURY/RISK/CUSTOMER/REGULATORY/OPERATIONS)
- **Multi-format export**: JSON and CSV with PII redaction and SHA-256 integrity hashing (I-12)
- **Dashboard KPIs**: Revenue, volume, compliance rate, NPS metrics with sparklines
- **Scheduled reports**: Create and manage recurring report schedules (DAILY/WEEKLY/MONTHLY/QUARTERLY)
- **Data aggregation**: Multi-source aggregation (SUM/AVERAGE/COUNT/MIN/MAX/PERCENTILE_95)
- **Schedule management**: Update schedule (always HITL — I-27)

## Invariants

| ID | Rule |
|----|------|
| I-01 | All amounts/scores as Decimal — never float |
| I-05 | API responses return amounts as strings |
| I-12 | Export file integrity via SHA-256 hash |
| I-24 | Audit log is append-only |
| I-27 | Schedule changes always HITL — Analytics Manager must approve |

## HITL Gates

| Action | Gate | Approver |
|--------|------|----------|
| update_schedule | HITL_REQUIRED | Analytics Manager |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /v1/reports/templates | List templates |
| POST | /v1/reports/templates | Create template |
| POST | /v1/reports/generate | Generate report |
| GET | /v1/reports/jobs/{job_id} | Get job status |
| GET | /v1/reports/jobs/{job_id}/export | Export report |
| GET | /v1/reports/dashboard/kpis | Dashboard KPIs |
| POST | /v1/reports/schedules | Create schedule |
| GET | /v1/reports/schedules | List schedules |
| POST | /v1/reports/schedules/{id} | Update schedule (HITL) |

## MCP Tools

- `report_analytics_generate` — Generate report from template
- `report_analytics_schedule` — Schedule a report
- `report_analytics_list_templates` — List all templates
- `report_analytics_export` — Export a report job

## References

- Service: services/reporting_analytics/
- Tests: tests/test_reporting_analytics/
- IL: IL-RAP-01
