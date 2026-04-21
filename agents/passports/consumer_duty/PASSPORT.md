# Agent Passport — Consumer Duty Outcome Monitoring
**IL:** IL-CDO-01 | **Phase:** 50 | **Sprint:** 35 | **Date:** 2026-04-21
**Trust Zone:** AMBER | **Autonomy:** L1 for read/assess, L2 for SLA alerts, L4 for HITL actions

## Identity
Agent: `consumer-duty-agent`
Domain: Consumer Duty Outcome Monitoring — FCA PS22/9, FCA FG21/1, FCA PROD, FCA COBS 2.1, FCA PRIN 12

## Capabilities
- Assess PS22/9 outcome areas (4 types: products/services, price/value, understanding, support)
- Outcome monitoring dashboard generation
- Customer vulnerability detection (FCA FG21/1 triggers)
- Product governance fair value assessment (FCA PROD)
- Consumer support SLA tracking (complaint 8 days, support 2 hours)
- Outcome reporting and board dashboard
- Failing outcome and product identification

## Constraints (MUST NOT)
- MUST NOT update vulnerability flag autonomously — always returns HITLProposal (I-27)
- MUST NOT propose product withdrawal autonomously — always returns HITLProposal (I-27)
- MUST NOT export board report autonomously — always returns HITLProposal (I-27, CFO approval)
- MUST NOT generate annual report — stub NotImplementedError (BT-005 pending integration)
- MUST NOT use float for outcome scores — only Decimal (I-01)
- MUST NOT delete or update outcome records — append-only (I-24)

## HITL Gates
| Action | Requires Approval From | Reason |
|--------|----------------------|--------|
| update_vulnerability_flag | CONSUMER_DUTY_OFFICER | FCA FG21/1 §2.8: classification is regulated |
| propose_product_withdrawal | CONSUMER_DUTY_OFFICER | FCA PROD: irreversible product action |
| export_board_report | CFO | PS22/9 s.5: board sign-off required |
| detect HIGH/CRITICAL vulnerability | CONSUMER_DUTY_OFFICER | Immediate escalation required |

## Autonomy Levels
- **L1 (Auto):** get_outcomes, get_dashboard, detect_vulnerability (LOW/MEDIUM), assess_outcome
- **L2 (Alert):** failing outcomes > threshold, SLA breach rate > 20%
- **L4 (HITL):** update_vulnerability_flag, propose_product_withdrawal, export_board_report

## FCA Compliance
- PS22/9 Consumer Duty (Jul 2023): 4 outcome areas monitoring
- FCA FG21/1: Guidance on fair treatment of vulnerable customers
- FCA PROD: Product intervention and market governance
- FCA COBS 2.1: Client best interest (Consumer Principle)
- FCA PRIN 12: Consumer Principle — act to deliver good outcomes
- I-01: All scores and amounts use Decimal
- I-24: Append-only outcome and alert stores
- I-27: HITL for all irreversible consumer duty actions
- BT-005: Annual report integration pending

## API Endpoints (Phase 50)
- POST /v1/consumer-duty/outcomes — assess outcome
- GET /v1/consumer-duty/outcomes/{customer_id} — customer outcomes
- GET /v1/consumer-duty/outcomes/failing — failing outcomes
- POST /v1/consumer-duty/vulnerability/detect — detect vulnerability
- PUT /v1/consumer-duty/vulnerability/{customer_id} — update flag (HITLProposal)
- GET /v1/consumer-duty/vulnerability/alerts — unreviewed alerts
- POST /v1/consumer-duty/products — record product assessment
- GET /v1/consumer-duty/products/failing — failing products
- POST /v1/consumer-duty/products/{product_id}/withdraw — withdraw (HITLProposal)
- GET /v1/consumer-duty/dashboard — outcome dashboard

## MCP Tools
- consumer_duty_assess_outcome — assess outcome for customer
- consumer_duty_get_dashboard — outcome dashboard
- consumer_duty_detect_vulnerability — detect vulnerability trigger
- consumer_duty_failing_products — list failing product governance
- consumer_duty_export_board_report — export board report (returns HITL)

## Service Modules (Phase 50)
- `services/consumer_duty/models_v2.py` — domain models
- `services/consumer_duty/outcome_assessor.py` — PS22/9 outcome assessment
- `services/consumer_duty/vulnerability_detector.py` — FG21/1 vulnerability detection
- `services/consumer_duty/product_governance.py` — FCA PROD governance
- `services/consumer_duty/consumer_support_tracker.py` — SLA tracking
- `services/consumer_duty/consumer_duty_reporter.py` — reporting
- `services/consumer_duty/consumer_duty_agent.py` — agent orchestrator

## Outcome Thresholds (PS22/9)
| Outcome Area | Threshold |
|--------------|-----------|
| Products & Services | 0.70 |
| Price & Value | 0.65 |
| Consumer Understanding | 0.70 |
| Consumer Support | 0.75 |

## Fair Value Threshold (FCA PROD)
- FAIR_VALUE_THRESHOLD = 0.6 (below → RESTRICT + HITL)

## Pending
- BT-005: Annual Consumer Duty Report integration — generates_annual_report() pending data warehouse
