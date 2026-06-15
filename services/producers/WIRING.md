# Producers wiring (S5.2) — closing audit gap #6

The 9 L2 client-facing agents accept three governance values as **injected,
keyword-only inputs**:

| agent input         | type               | how the agent receives it                |
|---------------------|--------------------|------------------------------------------|
| `compliance_result` | `ComplianceResult` | keyword param, **defaults to `PASS`**    |
| `confidence_score`  | `float`            | carried on the action `intent`           |
| `request_cost`      | `RequestCost`      | carried on the action `intent`           |

**Audit gap #6:** nothing *produced* `compliance_result` — the default-`PASS`
meant every action passed compliance silently. This package is the **producer
side of that seam**. The agents are **not edited**; the composition root computes
the three values and feeds them into the params/intent that already exist.

## What produces what

- **`ComplianceProducer`** → a real `ComplianceResult` (`PASS`/`FAIL`/`ESCALATE`/`N/A`),
  by orchestrating the existing L3 through three **injected Protocol ports**
  (`AMLCheckPort`, `SanctionsCheckPort`, `FraudCheckPort`). Aggregation: any
  `FAIL` → `FAIL`; else any `ESCALATE` → `ESCALATE`; else all-`N/A` → `N/A`; else
  `PASS`. This **replaces** the default-`PASS`.
- **`ConfidenceScorer`** → a deterministic `confidence_score ∈ [0,1]` from
  `match_source` / ambiguity / risk class (maps onto the ADR-049 §D4 bands).
- **`CostEstimator`** → a `RequestCost` (tokens + **Decimal** amount, no float)
  with an ADR-047 cost-cap awareness flag (`NONE`/`WARN`/`BREACH`).

## The L3 is wrapped, never edited

`services/producers/adapters.py` holds the **wired composition**: each adapter
delegates to an existing L3 service via a minimal *structural* Protocol (no
concrete L3 import, no L3 edits) and translates the L3 result into an opaque
`CheckOutcome`:

| adapter                 | wraps (L3)                                   | maps                                      |
|-------------------------|----------------------------------------------|-------------------------------------------|
| `AMLCheckAdapter`       | `services/aml` `TxMonitorService`            | `sanctions_block`→FAIL; any HITL flag→ESCALATE |
| `SanctionsCheckAdapter` | `services/sanctions_screening` `ScreeningEngine` | `CONFIRMED_MATCH`→FAIL; `POSSIBLE`/`ERROR`→ESCALATE |
| `FraudCheckAdapter`     | `services/fraud` `FraudScoringPort`          | `block`→FAIL; hold/APP-scam/HIGH-risk→ESCALATE |

**R-SEC:** the producer core carries only an opaque `subject_ref`; the sanctions
identity (name/nationality — PII) is resolved L3-side inside the adapter via
`SanctionsIdentityPort`, owned by the composition root. Outputs carry the L3
report/decision id + non-PII policy codes only — never a name, account, or raw
L3 reason string.

## Composition-root wiring (no agent edits)

```python
from decimal import Decimal

from services.producers import (
    ComplianceProducer, ConfidenceScorer, CostEstimator, ProducerBundle,
    AMLCheckAdapter, SanctionsCheckAdapter, FraudCheckAdapter, ComplianceCheckRequest,
)
from services.producers.confidence_scorer import ScoringSignals
from services.producers.ports import DEFAULT_COST_CAP

# Build the bundle once, from the live L3 services + the PII identity resolver.
bundle = ProducerBundle(
    compliance=ComplianceProducer(
        aml=AMLCheckAdapter(tx_monitor),                       # live services/aml
        sanctions=SanctionsCheckAdapter(screening_engine,      # live services/sanctions_screening
                                        identity=identity_resolver),
        fraud=FraudCheckAdapter(fraud_scorer),                 # live services/fraud
    ),
    confidence=ConfidenceScorer(),
    cost=CostEstimator(cost_cap=DEFAULT_COST_CAP, source=gateway_accounting),
)

# Per dispatch (after L1 router resolves the intent, before invoking the L2 agent):
outputs = bundle.produce(
    check_request=ComplianceCheckRequest(
        action=resolved.matched_intent, correlation_id=resolved.correlation_id,
        subject_ref=subject_ref, amount=amount,
    ),
    signals=ScoringSignals.from_resolved_intent(resolved, risk_class="STANDARD"),
    est_tokens=est_tokens,
)

# outputs map 1:1 onto the EXISTING agent seam — no agent code changes:
await agent.do_action(
    intent,  # carries outputs.confidence_score + outputs.request_cost
    compliance_result=outputs.compliance_result,  # ← REPLACES the default-PASS
)
```

`ProducerBundle.null()` is the safe pre-activation default (Null ports → `PASS`,
static cost source) for environments where the live L3 is not yet wired.
