"""Shared stub L3 ports for the producers tests — NO live L3, NO network."""

from __future__ import annotations

from decimal import Decimal

from services.agents._lineage import ComplianceResult
from services.producers.ports import (
    CheckOutcome,
    ComplianceCheckRequest,
    SanctionsIdentity,
)


class StubCheck:
    """A compliance check port that always returns a fixed result."""

    def __init__(self, result: ComplianceResult, *, ref: str = "stub") -> None:
        self._result = result
        self._ref = ref

    def check(self, request: ComplianceCheckRequest) -> CheckOutcome:
        return CheckOutcome(result=self._result, ref=self._ref)


class StaticIdentity:
    """SanctionsIdentityPort returning a fixed identity for any subject_ref."""

    def __init__(self, identity: SanctionsIdentity | None) -> None:
        self._identity = identity

    def resolve(self, subject_ref: str) -> SanctionsIdentity | None:
        return self._identity


def make_request(**overrides: object) -> ComplianceCheckRequest:
    base: dict[str, object] = {
        "action": "kyc_onboarding",
        "correlation_id": "corr-001",
        "subject_ref": "subj-opaque-001",
        "amount": Decimal("100"),
    }
    base.update(overrides)
    return ComplianceCheckRequest(**base)  # type: ignore[arg-type]
