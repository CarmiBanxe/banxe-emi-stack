# PASSPORT — ObservabilityAgent
**IL:** IL-OBS-01  
**Phase:** 53B  
**Sprint:** 38

## Identity
- **Agent ID:** observability-agent-v1
- **Domain:** Platform Observability
- **Autonomy Level:** L4 (Human Only for compliance alerts)
- **HITL Gate:** COMPLIANCE_OFFICER must acknowledge violations

## Capabilities
- `check_all()` — aggregate health of all P0 services
- `check_service(name)` — per-service health check
- `collect()` — platform metrics snapshot (tests, endpoints, MCP tools, passports, coverage)
- `scan()` — compliance invariant monitor (I-01..I-28)
- `acknowledge_alert()` — HITL L4 alert acknowledgement

## Constraints (MUST NOT)
- MUST NOT auto-remediate compliance violations (I-27)
- MUST NOT use float for coverage_pct (I-01)
- MUST NOT delete health_log or alert_log (I-24)
- MUST NOT push to Grafana without BT-008 resolved (NotImplementedError)

## Ports (Protocol DI)
- `HealthCheckPort` → `InMemoryHealthCheckPort` (stub)
- `ComplianceCheckPort` → `InMemoryComplianceCheckPort` (stub)

## Audit
- `HealthAggregator.health_log` — append-only (I-24)
- `ObservabilityAgent.alert_log` — append-only (I-24)

## BT Stubs
- BT-008: `MetricsCollector.push_to_grafana()` → raises NotImplementedError
