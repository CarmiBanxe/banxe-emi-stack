"""Null / static defaults — the no-live-L3 fallbacks all yield PASS / None."""

from __future__ import annotations

from services.agents._lineage import ComplianceResult
from services.producers.ports import (
    NullAMLCheck,
    NullFraudCheck,
    NullSanctionsCheck,
    NullSanctionsIdentity,
    StaticCostSource,
)
from tests.test_producers.conftest import make_request


def test_null_checks_pass() -> None:
    request = make_request()
    assert NullAMLCheck().check(request).result is ComplianceResult.PASS
    assert NullSanctionsCheck().check(request).result is ComplianceResult.PASS
    assert NullFraudCheck().check(request).result is ComplianceResult.PASS


def test_null_identity_resolves_none() -> None:
    assert NullSanctionsIdentity().resolve("subj-1") is None


def test_static_cost_source_returns_none() -> None:
    assert StaticCostSource().usage_for("key-1") is None
