from __future__ import annotations

import pytest

from services.runtime_gate.audit_sampling import InMemorySampler
from services.runtime_gate.errors import AuditPolicyError


def test_sampler_traces_at_full_rate():
    s = InMemorySampler(rate=1.0)
    assert s.trace("decision:audit_trail:0001") is True
    assert s.traces == ["decision:audit_trail:0001"]


def test_zero_rate_does_not_trace():
    s = InMemorySampler(rate=0.0)
    assert s.trace("decision:audit_trail:0002") is False
    assert s.traces == []


def test_rsec_rejects_pii_or_secret_refs():
    s = InMemorySampler(rate=1.0)
    for bad in (
        "alice@example.com",
        "secret=hunter2",
        "AKIAIOSFODNN7EXAMPLEABCDEFGHIJKLMNOPQRSTUVWX",
    ):
        with pytest.raises(AuditPolicyError):
            s.trace(bad)


def test_bad_rate_rejected():
    with pytest.raises(AuditPolicyError):
        InMemorySampler(rate=2.0)
