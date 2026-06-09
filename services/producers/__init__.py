"""
services/producers — compliance / confidence / cost PRODUCERS (S5.2).

Closes audit gap #6: the L2 client-facing agents accept ``compliance_result``
(default :data:`ComplianceResult.PASS`), ``confidence_score`` and
``request_cost`` as INJECTED inputs, but nothing PRODUCED them — a silent
default-PASS is an audit risk. This package is the producer side of that seam:

  • :class:`ComplianceProducer` — real PASS/FAIL/ESCALATE/N-A verdict, by
    orchestrating the existing L3 (AML / sanctions / fraud) via INJECTED ports.
  • :class:`ConfidenceScorer`   — deterministic confidence_score ∈ [0,1].
  • :class:`CostEstimator`      — RequestCost (tokens + Decimal) with cap-awareness.
  • :class:`ProducerBundle`     — the composition-root entry point; its outputs
    populate the agents' existing keyword params (no agent edits — see WIRING.md).

The L3 services are wrapped via ``services/producers/adapters.py`` (the WIRED
composition); the producer core depends only on Protocol ports and is unit-
testable with Null defaults (no live L3, no network).
"""

from __future__ import annotations

from services.producers.adapters import (
    AMLCheckAdapter,
    FraudCheckAdapter,
    SanctionsCheckAdapter,
)
from services.producers.bundle import ProducerBundle, ProducerOutputs
from services.producers.compliance_producer import (
    ComplianceProducer,
    ComplianceVerdict,
    aggregate,
)
from services.producers.confidence_scorer import ConfidenceScorer, ScoringSignals
from services.producers.cost_estimator import CostEstimate, CostEstimator
from services.producers.ports import (
    CheckOutcome,
    ComplianceCheckRequest,
    SanctionsIdentity,
)

__all__ = [
    "AMLCheckAdapter",
    "CheckOutcome",
    "ComplianceCheckRequest",
    "ComplianceProducer",
    "ComplianceVerdict",
    "ConfidenceScorer",
    "CostEstimate",
    "CostEstimator",
    "FraudCheckAdapter",
    "ProducerBundle",
    "ProducerOutputs",
    "SanctionsCheckAdapter",
    "SanctionsIdentity",
    "ScoringSignals",
    "aggregate",
]
