"""ComplianceProducer aggregation — the audit gap #6 closure proof.

Covers FAIL/ESCALATE/PASS/N-A combinations with injected stub L3 ports, and
proves a real verdict REPLACES the default-PASS.
"""

from __future__ import annotations

import pytest

from services.agents._lineage import ComplianceResult
from services.producers.compliance_producer import (
    ComplianceProducer,
    aggregate,
)
from services.producers.ports import CheckOutcome
from tests.test_producers.conftest import StubCheck, make_request

R = ComplianceResult


@pytest.mark.parametrize(
    ("sanctions", "aml", "fraud", "expected"),
    [
        (R.PASS, R.PASS, R.PASS, R.PASS),
        (R.FAIL, R.PASS, R.PASS, R.FAIL),  # sanctions confirmed → FAIL
        (R.PASS, R.ESCALATE, R.PASS, R.ESCALATE),  # AML SAR → ESCALATE
        (R.PASS, R.PASS, R.ESCALATE, R.ESCALATE),  # fraud hold → ESCALATE
        (R.FAIL, R.ESCALATE, R.PASS, R.FAIL),  # FAIL dominates ESCALATE
        (R.ESCALATE, R.ESCALATE, R.ESCALATE, R.ESCALATE),
        (R.NA, R.NA, R.NA, R.NA),  # nothing applicable
        (R.NA, R.PASS, R.NA, R.PASS),  # one applicable PASS → PASS
        (R.NA, R.ESCALATE, R.NA, R.ESCALATE),
        (R.NA, R.FAIL, R.NA, R.FAIL),
    ],
)
def test_aggregation_combinations(
    sanctions: ComplianceResult,
    aml: ComplianceResult,
    fraud: ComplianceResult,
    expected: ComplianceResult,
) -> None:
    producer = ComplianceProducer(
        sanctions=StubCheck(sanctions),
        aml=StubCheck(aml),
        fraud=StubCheck(fraud),
    )
    verdict = producer.evaluate(make_request())
    assert verdict.result is expected
    assert verdict.correlation_id == "corr-001"
    assert len(verdict.checks) == 3


def test_aggregate_empty_is_pass() -> None:
    # Defensive: an empty outcome set is not an all-N/A set → PASS.
    assert aggregate(()) is ComplianceResult.PASS


def test_default_ports_pass_but_are_explicit_producers() -> None:
    # The Null default still yields PASS, but now via an explicit producer path.
    verdict = ComplianceProducer().evaluate(make_request())
    assert verdict.result is ComplianceResult.PASS


def test_sanctions_hit_is_not_default_pass() -> None:
    # AUDIT PROOF: a sanctions hit yields FAIL, NOT the default-PASS.
    producer = ComplianceProducer(sanctions=StubCheck(ComplianceResult.FAIL))
    assert producer.evaluate(make_request()).result is ComplianceResult.FAIL


def test_aml_hit_escalates_not_pass() -> None:
    # AUDIT PROOF: an AML hit needing MLRO yields ESCALATE, NOT default-PASS.
    producer = ComplianceProducer(aml=StubCheck(ComplianceResult.ESCALATE))
    assert producer.evaluate(make_request()).result is ComplianceResult.ESCALATE


def test_outcomes_carry_opaque_refs_only() -> None:
    outcome = CheckOutcome(result=ComplianceResult.FAIL, ref="rep_abc123", reason_codes=("X",))
    assert outcome.ref == "rep_abc123"
    assert outcome.reason_codes == ("X",)
