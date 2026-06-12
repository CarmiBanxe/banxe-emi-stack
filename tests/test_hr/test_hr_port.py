"""Tests for the HR domain port (services/hr/hr_port.py).

Covers the routine read/write ops (training status, conduct attestation), the
prepare-only SMF proposal, and the CEO-token-gated SMF appointment commit — including
the structural guarantee that ``apply_smf_appointment`` REFUSES to appoint an SMF holder
without a CEO token (defence-in-depth beneath the agent gate), plus the not-found and
transient-failure error paths and the read-only SM&CR handle double. 100% coverage.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from services.hr.hr_port import (
    CEOAuthorizationRequired,
    ConductAttestation,
    ConductRuleTier,
    EmployeeNotFound,
    HRSourceUnavailable,
    InMemoryHRPort,
    InMemorySMCRReadHandle,
    SMFAppointment,
    SMFAppointmentProposal,
    TrainingStatus,
)


def make_port() -> InMemoryHRPort:
    return InMemoryHRPort()


# ── Routine reads (training) ────────────────────────────────────────────────────


async def test_get_training_status_returns_record():
    port = make_port()
    when = datetime(2026, 6, 12, tzinfo=UTC)
    port.add_training("EMP-1", "AML-101", completed=True, completed_at=when)

    status = await port.get_training_status("EMP-1", "AML-101")

    assert isinstance(status, TrainingStatus)
    assert status.completed is True
    assert status.completed_at == when
    assert port.get_training_status_calls == [("EMP-1", "AML-101")]


async def test_get_training_status_unknown_employee_raises():
    port = make_port()
    with pytest.raises(EmployeeNotFound) as ei:
        await port.get_training_status("EMP-X", "AML-101")
    assert ei.value.correlation_id == "EMP-X"


async def test_get_training_status_source_unavailable_raises():
    port = make_port()
    port.set_unavailable(HRSourceUnavailable("hris down", correlation_id="corr-1"))
    with pytest.raises(HRSourceUnavailable):
        await port.get_training_status("EMP-1", "AML-101")


# ── Routine writes (conduct attestation) ────────────────────────────────────────


async def test_record_conduct_attestation_returns_record():
    port = make_port()
    att = await port.record_conduct_attestation("EMP-1", ConductRuleTier.TIER_1, attested=True)

    assert isinstance(att, ConductAttestation)
    assert att.attested is True
    assert att.tier is ConductRuleTier.TIER_1
    assert att.recorded_at.tzinfo is not None
    assert port.conduct_attestation_calls == [("EMP-1", ConductRuleTier.TIER_1, True)]


async def test_record_conduct_attestation_source_unavailable_raises():
    port = make_port()
    port.set_unavailable(HRSourceUnavailable("hris down", correlation_id="corr-1"))
    with pytest.raises(HRSourceUnavailable):
        await port.record_conduct_attestation("EMP-1", ConductRuleTier.TIER_2, attested=False)


# ── SMF proposal (prepare only — no token, appoints nothing) ────────────────────


async def test_propose_smf_appointment_prepares_token_less_proposal():
    port = make_port()
    proposal = port.propose_smf_appointment("SMF1", "CAND-1", incumbent_id="OLD-CEO")

    assert isinstance(proposal, SMFAppointmentProposal)
    assert proposal.role == "SMF1"
    assert proposal.candidate_id == "CAND-1"
    assert proposal.incumbent_id == "OLD-CEO"
    assert proposal.prepared_at.tzinfo is not None
    assert port.propose_calls == [("SMF1", "CAND-1")]
    # prepare-only: nothing was appointed.
    assert port.apply_calls == []


# ── SMF appointment commit (CEO-token-gated) ────────────────────────────────────


async def test_apply_smf_appointment_with_token_commits():
    port = make_port()
    proposal = port.propose_smf_appointment("SMF1", "CAND-1")
    appointment = port.apply_smf_appointment(proposal, "ceo-sig-abc")  # noqa: S106

    assert isinstance(appointment, SMFAppointment)
    assert appointment.authorized is True
    assert appointment.role == "SMF1"
    assert appointment.candidate_id == "CAND-1"
    assert appointment.appointed_at.tzinfo is not None
    assert port.apply_calls == [("SMF-PROP-SMF1-CAND-1", "CAND-1")]


async def test_apply_smf_appointment_without_token_refuses():
    # Structural guarantee: no SMF holder is appointed without a CEO token (SM&CR).
    port = make_port()
    proposal = port.propose_smf_appointment("SMF1", "CAND-1")
    with pytest.raises(CEOAuthorizationRequired) as ei:
        port.apply_smf_appointment(proposal, "")
    assert ei.value.correlation_id == "SMF-PROP-SMF1-CAND-1"
    assert port.apply_calls == []  # never applied


# ── Read-only SM&CR handle double ───────────────────────────────────────────────


async def test_smcr_read_handle_reads_and_records_lookups():
    sentinel = object()
    handle = InMemorySMCRReadHandle(senior_managers={"CAND-1": sentinel})

    assert handle.get_senior_manager("CAND-1") is sentinel
    assert handle.get_senior_manager("UNKNOWN") is None
    assert handle.get_senior_manager_calls == ["CAND-1", "UNKNOWN"]
