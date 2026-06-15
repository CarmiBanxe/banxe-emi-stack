"""Tests for the MLSignalPort CONTRACT + InMemoryMLSignalPort (services/ml_pipeline).

Covers every conformance rule of the I-27 dual-sign-off port: read-only drift signals
(known / unknown → ModelNotFound), propose_retraining (no token, applies nothing; urgency
mapping; unknown → ModelNotFound), the dual CRO+CTO sign-off on apply_model_update (both
tokens → applied; missing CRO / CTO / both → DualSignOffRequired with NOTHING applied; unknown
model → ModelNotFound), and the transient signal-source failure (MLSignalSourceUnavailable) on
every op. R-SEC: the sign-off tokens never ride a returned ModelUpdateResult. I-10: the port is
in-memory only — no real ML training framework.
"""

from __future__ import annotations

import pytest

from services.ml_pipeline.ml_signal_port import (
    DriftSeverity,
    DriftSignal,
    DualSignOffRequired,
    InMemoryMLSignalPort,
    MLSignalSourceUnavailable,
    ModelNotFound,
    ModelUpdateResult,
    RetrainingProposal,
    RetrainingUrgency,
)

_CRO_TOKEN = "cro-signoff-opaque-token"
_CTO_TOKEN = "cto-signoff-opaque-token"


def _signal(model_id: str, severity: DriftSeverity) -> DriftSignal:
    return DriftSignal(
        model_id=model_id,
        drift_detected=severity is not DriftSeverity.NONE,
        severity=severity,
        metric_summary=f"{model_id} severity {severity.value}",
    )


def _port(**models: DriftSeverity) -> InMemoryMLSignalPort:
    """Build an in-memory port seeded with one drift signal per named model."""
    return InMemoryMLSignalPort(signals={mid: [_signal(mid, sev)] for mid, sev in models.items()})


# ── get_drift_signals ──────────────────────────────────────────────────────


async def test_get_drift_signals_known_returns_signals():
    port = _port(fraud_v3=DriftSeverity.HIGH)
    signals = await port.get_drift_signals("fraud_v3")
    assert [s.severity for s in signals] == [DriftSeverity.HIGH]
    assert signals[0].model_id == "fraud_v3"


async def test_get_drift_signals_unknown_raises_model_not_found():
    port = _port(fraud_v3=DriftSeverity.LOW)
    with pytest.raises(ModelNotFound) as exc:
        await port.get_drift_signals("nope")
    assert exc.value.correlation_id == "drift:nope"


async def test_get_drift_signals_source_unavailable_reraises():
    port = _port(fraud_v3=DriftSeverity.LOW)
    port.fail_with = MLSignalSourceUnavailable("down", correlation_id="x")
    with pytest.raises(MLSignalSourceUnavailable):
        await port.get_drift_signals("fraud_v3")


# ── propose_retraining (no token; applies nothing) ─────────────────────────


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        (DriftSeverity.CRITICAL, RetrainingUrgency.URGENT),
        (DriftSeverity.HIGH, RetrainingUrgency.URGENT),
        (DriftSeverity.MODERATE, RetrainingUrgency.ELEVATED),
        (DriftSeverity.LOW, RetrainingUrgency.ROUTINE),
        (DriftSeverity.NONE, RetrainingUrgency.ROUTINE),
    ],
)
async def test_propose_retraining_maps_urgency(severity, expected):
    port = _port(model_a=severity)
    proposal = await port.propose_retraining("model_a")
    assert isinstance(proposal, RetrainingProposal)
    assert proposal.model_id == "model_a"
    assert proposal.urgency is expected
    # Proposing applies NOTHING (I-27): no model update is recorded.
    assert port.applied == []


async def test_propose_retraining_empty_signals_is_routine():
    port = InMemoryMLSignalPort(signals={"model_a": []})
    proposal = await port.propose_retraining("model_a")
    assert proposal.urgency is RetrainingUrgency.ROUTINE


async def test_propose_retraining_unknown_raises_model_not_found():
    port = _port(model_a=DriftSeverity.LOW)
    with pytest.raises(ModelNotFound) as exc:
        await port.propose_retraining("ghost")
    assert exc.value.correlation_id == "propose:ghost"


async def test_propose_retraining_source_unavailable_reraises():
    port = _port(model_a=DriftSeverity.LOW)
    port.fail_with = MLSignalSourceUnavailable("down", correlation_id="x")
    with pytest.raises(MLSignalSourceUnavailable):
        await port.propose_retraining("model_a")


# ── apply_model_update (dual CRO+CTO sign-off; NEVER autonomous) ───────────


async def _proposal(port: InMemoryMLSignalPort, model_id: str = "model_a") -> RetrainingProposal:
    return await port.propose_retraining(model_id)


async def test_apply_with_both_tokens_applies_update():
    port = _port(model_a=DriftSeverity.HIGH)
    proposal = await _proposal(port)
    result = await port.apply_model_update(proposal, _CRO_TOKEN, _CTO_TOKEN)
    assert isinstance(result, ModelUpdateResult)
    assert result.applied is True
    assert result.model_id == "model_a"
    assert port.applied == [result]
    # R-SEC: neither sign-off token rides the returned result.
    assert _CRO_TOKEN not in repr(result)
    assert _CTO_TOKEN not in repr(result)


async def test_apply_missing_cro_raises_and_applies_nothing():
    port = _port(model_a=DriftSeverity.HIGH)
    proposal = await _proposal(port)
    with pytest.raises(DualSignOffRequired):
        await port.apply_model_update(proposal, "", _CTO_TOKEN)
    assert port.applied == []


async def test_apply_missing_cto_raises_and_applies_nothing():
    port = _port(model_a=DriftSeverity.HIGH)
    proposal = await _proposal(port)
    with pytest.raises(DualSignOffRequired):
        await port.apply_model_update(proposal, _CRO_TOKEN, "")
    assert port.applied == []


async def test_apply_missing_both_raises_and_applies_nothing():
    port = _port(model_a=DriftSeverity.HIGH)
    proposal = await _proposal(port)
    with pytest.raises(DualSignOffRequired) as exc:
        await port.apply_model_update(proposal, "", "")
    assert exc.value.correlation_id == f"apply:{proposal.proposal_id}"
    assert port.applied == []


async def test_apply_unknown_model_with_both_tokens_raises_model_not_found():
    port = _port(model_a=DriftSeverity.HIGH)
    ghost = RetrainingProposal(
        proposal_id="prop-ghost-1",
        model_id="ghost",
        urgency=RetrainingUrgency.URGENT,
        rationale="n/a",
    )
    with pytest.raises(ModelNotFound):
        await port.apply_model_update(ghost, _CRO_TOKEN, _CTO_TOKEN)
    assert port.applied == []


async def test_apply_source_unavailable_reraises():
    port = _port(model_a=DriftSeverity.HIGH)
    proposal = await _proposal(port)
    port.fail_with = MLSignalSourceUnavailable("down", correlation_id="x")
    with pytest.raises(MLSignalSourceUnavailable):
        await port.apply_model_update(proposal, _CRO_TOKEN, _CTO_TOKEN)


async def test_apply_increments_version_ref():
    port = _port(model_a=DriftSeverity.HIGH, model_b=DriftSeverity.HIGH)
    p_a = await _proposal(port, "model_a")
    p_b = await _proposal(port, "model_b")
    r_a = await port.apply_model_update(p_a, _CRO_TOKEN, _CTO_TOKEN)
    r_b = await port.apply_model_update(p_b, _CRO_TOKEN, _CTO_TOKEN)
    assert r_a.version_ref == "model_a@v1"
    assert r_b.version_ref == "model_b@v2"
