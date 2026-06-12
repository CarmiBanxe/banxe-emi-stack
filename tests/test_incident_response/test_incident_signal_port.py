"""Tests for the read-only IncidentSignalPort
(services/incident_response/incident_signal_port.py).

Covers the full read + classify surface: get_incidents (all + severity filter +
source unavailability), get_incident (found / not-found / unavailable), the
classify_severity band helper across every band and its boundaries, the error
hierarchy correlation_id, and the in-memory double's spies. The port exposes NO
close/suppress seam — auto-closure is impossible by construction.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.incident_response.incident_signal_port import (
    IncidentNotFound,
    IncidentSeverity,
    IncidentSignal,
    IncidentSignalPortError,
    IncidentSource,
    IncidentStatus,
    InMemoryIncidentSignalPort,
    SignalSourceUnavailable,
)


def make_port() -> InMemoryIncidentSignalPort:
    return InMemoryIncidentSignalPort()


# ── classify_severity bands (pure read-only helper) ────────────────────────────


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, IncidentSeverity.LOW),
        (39, IncidentSeverity.LOW),
        (40, IncidentSeverity.MEDIUM),
        (69, IncidentSeverity.MEDIUM),
        (70, IncidentSeverity.HIGH),
        (84, IncidentSeverity.HIGH),
        (85, IncidentSeverity.CRITICAL),
        (100, IncidentSeverity.CRITICAL),
    ],
)
def test_classify_severity_bands(score, expected):
    port = make_port()
    assert port.classify_severity(score) is expected
    assert port.classify_calls == [score]


# ── get_incidents (read; filter; unavailability) ───────────────────────────────


async def test_get_incidents_returns_all_unfiltered():
    port = make_port()
    port.add_incident("INC-1", signal_score=10)
    port.add_incident("INC-2", signal_score=90)

    incidents = await port.get_incidents()

    assert {i.incident_id for i in incidents} == {"INC-1", "INC-2"}
    assert port.get_incidents_calls == [None]


async def test_get_incidents_filters_by_severity():
    port = make_port()
    port.add_incident("INC-LOW", signal_score=10)
    port.add_incident("INC-CRIT", signal_score=92)

    crit = await port.get_incidents(IncidentSeverity.CRITICAL)

    assert [i.incident_id for i in crit] == ["INC-CRIT"]
    assert crit[0].severity is IncidentSeverity.CRITICAL
    assert port.get_incidents_calls == [IncidentSeverity.CRITICAL]


async def test_get_incidents_raises_when_source_unavailable():
    port = make_port()
    port.set_unavailable(SignalSourceUnavailable("siem down", correlation_id="corr-1"))
    with pytest.raises(SignalSourceUnavailable):
        await port.get_incidents()


# ── get_incident (read; not-found; unavailability) ─────────────────────────────


async def test_get_incident_returns_signal():
    port = make_port()
    port.add_incident(
        "INC-7",
        signal_score=88,
        source=IncidentSource.ATO_ENGINE,
        status=IncidentStatus.OPEN,
        detected_at=datetime(2026, 6, 12, tzinfo=UTC),
    )
    signal = await port.get_incident("INC-7")

    assert isinstance(signal, IncidentSignal)
    assert signal.severity is IncidentSeverity.CRITICAL
    assert signal.source is IncidentSource.ATO_ENGINE
    assert port.get_incident_calls == ["INC-7"]


async def test_get_incident_not_found_raises_with_correlation_id():
    port = make_port()
    with pytest.raises(IncidentNotFound) as exc:
        await port.get_incident("nope")
    assert exc.value.correlation_id == "nope"


async def test_get_incident_raises_when_source_unavailable():
    port = make_port()
    port.add_incident("INC-1", signal_score=10)
    port.set_unavailable(SignalSourceUnavailable("transient", correlation_id="c"))
    with pytest.raises(SignalSourceUnavailable):
        await port.get_incident("INC-1")


# ── add_incident: explicit severity bypasses classify ──────────────────────────


def test_add_incident_explicit_severity_skips_classify():
    port = make_port()
    signal = port.add_incident("INC-X", signal_score=10, severity=IncidentSeverity.CRITICAL)
    # Explicit severity is honoured even though the score would classify LOW.
    assert signal.severity is IncidentSeverity.CRITICAL
    assert port.classify_calls == []  # classify spy not polluted by add_incident


def test_add_incident_default_severity_uses_classify_and_clears_spy():
    port = make_port()
    signal = port.add_incident("INC-Y", signal_score=72)
    assert signal.severity is IncidentSeverity.HIGH
    # add_incident clears the classify spy so caller-facing assertions stay clean.
    assert port.classify_calls == []


# ── error hierarchy ────────────────────────────────────────────────────────────


def test_error_base_carries_correlation_id():
    err = IncidentSignalPortError("boom", correlation_id="corr-9")
    assert err.correlation_id == "corr-9"
    assert isinstance(IncidentNotFound("x", correlation_id="c"), IncidentSignalPortError)
    assert isinstance(SignalSourceUnavailable("x", correlation_id="c"), IncidentSignalPortError)
