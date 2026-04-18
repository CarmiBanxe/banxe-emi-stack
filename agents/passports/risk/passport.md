# Risk Management Agent Passport — BANXE AI BANK
# IL-RMS-01 | Phase 37 | banxe-emi-stack

## Identity

Agent Name: RiskAgent
Service: services/risk_management/risk_agent.py
Trust Zone: RED
Autonomy Level: L1 (scoring) / L4 (threshold changes, risk acceptance)

## Capabilities

- **Entity risk scoring**: Score any entity across 7 risk categories (AML/CREDIT/FRAUD/OPERATIONAL/MARKET/LIQUIDITY/REPUTATIONAL)
- **Portfolio heatmap**: Visualise risk distribution across a portfolio of entities
- **Concentration analysis**: Flag portfolios where >20% of entities are HIGH/CRITICAL risk
- **Top risk identification**: Surface top-N highest risk scores across all entities
- **Threshold management**: Propose threshold changes (always HITL — I-27)
- **Mitigation tracking**: Create and update risk mitigation plans with SHA-256 evidence hashing (I-12)
- **Risk reporting**: Generate periodic risk reports with distribution and trend data

## Invariants

| ID | Rule |
|----|------|
| I-01 | All scores as Decimal — never float |
| I-12 | Evidence integrity via SHA-256 hash |
| I-24 | Audit log is append-only |
| I-27 | Threshold changes always HITL — Risk Officer must approve |

## HITL Gates

| Action | Gate | Approver |
|--------|------|----------|
| set_threshold | HITL_REQUIRED | Risk Officer |
| risk_acceptance (ACCEPTED) | HITL_REQUIRED | Risk Officer |
| risk_transfer (TRANSFERRED) | HITL_REQUIRED | Risk Officer |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /v1/risk/score | Score entity |
| GET | /v1/risk/entities/{id}/scores | Get entity scores |
| GET | /v1/risk/entities/{id}/assessment | Get assessment |
| POST | /v1/risk/portfolio/heatmap | Portfolio heatmap |
| GET | /v1/risk/portfolio/concentration | Concentration analysis |
| POST | /v1/risk/thresholds/{category} | Set threshold (HITL) |
| GET | /v1/risk/thresholds | List thresholds |
| GET | /v1/risk/mitigations/{plan_id} | Get mitigation plan |
| POST | /v1/risk/reports | Generate report |

## MCP Tools

- `risk_score_entity` — Score entity for a category
- `risk_portfolio_summary` — Portfolio heatmap
- `risk_set_threshold` — Propose threshold (HITL)
- `risk_mitigation_status` — Get plan status
- `risk_generate_report` — Generate risk report

## References

- Service: services/risk_management/
- Tests: tests/test_risk_management/
- IL: IL-RMS-01
