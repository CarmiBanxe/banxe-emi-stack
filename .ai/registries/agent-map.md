# Agent Map — banxe-emi-stack
# Source: agents/compliance/swarm.yaml, .claude/agents/, services/hitl/
# Created: 2026-04-10
# Migration Phase: 4
# Purpose: All AI agents, soul files, authority levels, HITL gates

## Agent inventory

### Claude Code agents (.claude/agents/ — 2 agents)

| Agent | File | Autonomy | Domain | Human double |
|-------|------|----------|--------|-------------|
| ReconcAgent | `.claude/agents/reconciliation-agent.md` | L1 Auto (alert on DISCREPANCY) | Safeguarding reconciliation | MLRO |
| ReportingAgent | `.claude/agents/reporting-agent.md` | L1 Auto (CFO review for upload) | FIN060 PDF generation | CFO |

### Compliance Swarm (agents/compliance/ — 7 soul agents)

Defined in `agents/compliance/swarm.yaml` — trust zone: RED

| Agent | Soul file | Autonomy | Layer | Human double | Depends on |
|-------|-----------|----------|-------|-------------|------------|
| MLRO Agent (coordinator) | `soul/mlro_agent.soul.md` | L2 | Coordinator | MLRO | — |
| Jube Adapter Agent | `soul/jube_adapter_agent.soul.md` | L3 | Layer 1 (adapter) | CTIO | — (parallel) |
| Sanctions Check Agent | `soul/sanctions_check_agent.soul.md` | L3 | Layer 1 (adapter) | MLRO | — (parallel) |
| AML Check Agent | `soul/aml_check_agent.soul.md` | L3 | Layer 2 (domain) | Compliance Officer | jube_adapter_agent |
| Transaction Monitor Agent | `soul/tm_agent.soul.md` | L3 | Layer 2 (domain) | Compliance Officer | jube_adapter_agent |
| CDD Review Agent | `soul/cdd_review_agent.soul.md` | L2 | Layer 2 (domain) | Compliance Officer | sanctions_check_agent |
| Fraud Detection Agent | `soul/fraud_detection_agent.soul.md` | L3 | Layer 2 (domain) | Fraud Analyst | jube_adapter_agent, tm_agent |

### Compliance workflows (agents/compliance/workflows/)

| Workflow | File | Schedule |
|----------|------|----------|
| Monthly Compliance Review | `workflows/monthly_compliance_review.yaml` | Monthly |
| Quarterly Board Report | `workflows/quarterly_board_report.yaml` | Quarterly |

## Authority matrix

| Level | Label | Description | Examples |
|-------|-------|-------------|----------|
| L1 | Auto | Fully automated, no human approval | Fetch balance, parse statement, log event |
| L2 | Alert | Auto-execute, alert human on anomaly | DISCREPANCY alert → MLRO, CDD review |
| L3 | Propose | AI proposes, human reviews if flagged | AML check, fraud scoring, sanctions match |
| L4 | Human Only | Human-only action, AI cannot execute | SAR filing, discrepancy resolution, FIN060 sign-off |

## HITL gates (from swarm.yaml)

| Gate | Required roles | Timeout | Escalation |
|------|---------------|---------|------------|
| SAR_filing | MLRO | 24 hours | → CEO |
| AML_threshold_change | MLRO, CEO | 4 hours | — |
| sanctions_reversal | MLRO, CEO | 1 hour | — |
| PEP_onboarding | MLRO | 48 hours | — |
| board_report_sign_off | MLRO, BOARD | 3 days | — |

## HITL service (services/hitl/ — 5 files)

| File | Purpose |
|------|---------|
| `hitl_port.py` | HITLPort protocol definition |
| `hitl_service.py` | HITL orchestration service |
| `feedback_loop.py` | AI learning from CTIO decisions (IL-056) |
| `org_roles.py` | Organizational role definitions |

Key invariant: AI agents operate in PROPOSES mode only (I-27). All final decisions require human approval through HITL gates.

## Agent tools

| Tool | Used by | Purpose |
|------|---------|---------|
| hitl_check_gate | MLRO, Sanctions, AML, TM, CDD, Fraud | Human approval gate |
| clickhouse_log_event | All agents | Audit trail (append-only, I-24) |
| n8n_trigger_workflow | MLRO | Notification workflows |
| marble_create_case | MLRO, AML | Case management escalation |
| midaz_subscribe_events | Jube Adapter | Ledger event subscription |
| jube_post_transaction | Jube Adapter | Fraud rule evaluation |
| watchman_search | Sanctions | OFAC/sanctions list search |
| fraud_scoring_port | Fraud Detection | Sardine.ai scoring |
| rag_query_kb | AML, TM, CDD, Fraud | Compliance knowledge base query |

## Knowledge base

- Type: ChromaDB
- Collection: `banxe_compliance_kb`
- Embedding model: `all-MiniLM-L6-v2`
- Context index: `agents/compliance/agent_context.json`
- Top-K: 5

## Memory & audit

- Memory: PostgreSQL (`compliance_swarm_sessions` table)
- Audit: ClickHouse (`compliance_swarm_events` table, 5yr retention per I-08)

---
*Last updated: 2026-04-10 (Phase 4 migration)*
