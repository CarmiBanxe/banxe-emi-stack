# Risk Assessment — [TITLE]
# Ticket: [IL-XX-NN]
# Author: | Date: | Review cycle: pre-deploy / quarterly / incident-driven

---

## Domain
_Which domain: ledger / recon / AML / KYC / reporting / auth / infra / all_

## Risk Summary
_One paragraph: what is the risk, in what scenario does it materialise, and what is the impact?_

## Worst-Case Scenario
_If this risk materialises fully: what is the blast radius?_

| Dimension | Worst case |
|-----------|-----------|
| Financial loss | |
| Regulatory breach | |
| Customer impact | |
| Reputational | |
| Recovery time | |

## Likelihood Assessment

| Factor | Score (1-5) | Notes |
|--------|-------------|-------|
| Historical frequency | | |
| System complexity | | |
| External dependencies | | |
| Team familiarity | | |
| **Overall likelihood** | | |

## Impact Assessment

| Factor | Score (1-5) | Notes |
|--------|-------------|-------|
| Financial exposure | | |
| Regulatory exposure | | |
| Customer harm | | |
| Operational disruption | | |
| **Overall impact** | | |

**Risk score**: Likelihood × Impact = [NN]

---

## Existing Controls
_Controls already in place that reduce likelihood or impact._

| Control | Type | Effectiveness |
|---------|------|--------------|
| | preventive / detective / corrective | high / medium / low |

## New Controls Proposed
_Controls this assessment recommends adding._

| Control | Type | Owner | Due |
|---------|------|-------|-----|
| | | | |

## Test Coverage
_Which tests currently cover this risk area? What is missing?_

## Monitoring
_What metrics or alerts detect this risk materialising?_

## Rollback Readiness
_Can the change be rolled back within SLA if this risk materialises?_

- [ ] Rollback plan exists and is tested
- [ ] Rollback time < [X] minutes
- [ ] Data consistency after rollback confirmed

## Approvals Required

| Role | Required for | Sign-off |
|------|-------------|---------|
| CTIO | infrastructure / security risks | |
| MLRO | AML / KYC / reporting risks | |
| CFO | financial exposure | |
| CEO | combined risk score > 20 | |
