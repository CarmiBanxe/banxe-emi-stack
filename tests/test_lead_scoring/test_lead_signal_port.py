"""LeadSignalPort contract test suite — 100% coverage over
services/lead_scoring/lead_signal_port.py.

Validates the READ-ONLY contract and the InMemoryLeadSignalPort double:
get_active_leads (threshold filter + highest-score-first ordering + range guard),
get_lead_score (known / unknown → LeadNotFound), the fail_on_call provider-error path,
the value types (Decimal numerics, opaque handles), the error hierarchy, and the read-only
INVARIANT (the port exposes NO contact / outreach / nurture / write method).

asyncio_mode = "auto" (pyproject.toml): every ``async def test_*`` is auto-collected.
"""

from __future__ import annotations

from decimal import Decimal
import inspect

import pytest

from services.lead_scoring.lead_signal_port import (
    InMemoryLeadSignalPort,
    LeadNotFound,
    LeadScore,
    LeadScoreBand,
    LeadSignal,
    LeadSignalCode,
    LeadSignalPort,
    LeadSignalPortError,
    LeadStage,
    ScoredLead,
)

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _score(
    lead_id: str,
    *,
    cohort: str = "organic-eu",
    score: str = "0.50",
    band: LeadScoreBand = LeadScoreBand.WARM,
    stage: LeadStage = LeadStage.ONBOARDING,
) -> LeadScore:
    return LeadScore(
        lead_id=lead_id,
        cohort=cohort,
        score=Decimal(score),
        band=band,
        stage=stage,
        signals=(
            LeadSignal(code=LeadSignalCode.FEATURE_ENGAGEMENT, weight=Decimal("0.40"), detail="e"),
        ),
    )


# ---------------------------------------------------------------------------
# 1. get_active_leads — threshold filter + ordering
# ---------------------------------------------------------------------------


async def test_active_leads_filters_by_threshold_and_orders_high_first() -> None:
    port = InMemoryLeadSignalPort(
        scores={
            "a": _score("a", score="0.90", band=LeadScoreBand.HOT, stage=LeadStage.ACTIVE),
            "b": _score("b", score="0.50"),
            "c": _score("c", score="0.10", band=LeadScoreBand.COLD, stage=LeadStage.SIGNUP),
        }
    )
    result = await port.get_active_leads(Decimal("0.40"))

    assert [lead.lead_id for lead in result] == ["a", "b"]  # c (0.10) excluded; ordered desc
    assert all(isinstance(lead, ScoredLead) for lead in result)
    assert result[0].score == Decimal("0.90")
    assert result[0].band is LeadScoreBand.HOT
    assert result[0].stage is LeadStage.ACTIVE
    assert result[0].cohort == "organic-eu"


async def test_active_leads_threshold_zero_returns_all() -> None:
    port = InMemoryLeadSignalPort()  # default seed: 2 leads
    result = await port.get_active_leads(Decimal("0"))
    assert len(result) == 2


async def test_active_leads_high_threshold_returns_empty() -> None:
    port = InMemoryLeadSignalPort()
    result = await port.get_active_leads(Decimal("1"))
    assert result == []


@pytest.mark.parametrize("bad", [Decimal("-0.01"), Decimal("1.01")])
async def test_active_leads_threshold_out_of_range_raises(bad: Decimal) -> None:
    port = InMemoryLeadSignalPort()
    with pytest.raises(LeadSignalPortError, match="threshold out of range"):
        await port.get_active_leads(bad)


# ---------------------------------------------------------------------------
# 2. get_lead_score — known / unknown
# ---------------------------------------------------------------------------


async def test_get_lead_score_known_returns_score() -> None:
    port = InMemoryLeadSignalPort(scores={"lead-x": _score("lead-x", score="0.77")})
    out = await port.get_lead_score("lead-x")
    assert isinstance(out, LeadScore)
    assert out.lead_id == "lead-x"
    assert out.score == Decimal("0.77")
    assert out.signals[0].code is LeadSignalCode.FEATURE_ENGAGEMENT


async def test_get_lead_score_unknown_raises_lead_not_found() -> None:
    port = InMemoryLeadSignalPort(scores={})
    with pytest.raises(LeadNotFound, match="Unknown lead"):
        await port.get_lead_score("nope")


async def test_default_seed_has_expected_leads() -> None:
    port = InMemoryLeadSignalPort()
    out = await port.get_lead_score("lead-1001")
    assert out.band is LeadScoreBand.HOT
    assert out.stage is LeadStage.ACTIVATED
    assert out.score == Decimal("0.88")
    assert len(out.signals) == 2


# ---------------------------------------------------------------------------
# 3. fail_on_call — provider-error path on every read
# ---------------------------------------------------------------------------


async def test_fail_on_call_raises_on_active_leads() -> None:
    port = InMemoryLeadSignalPort(fail_on_call=True)
    with pytest.raises(LeadSignalPortError, match="configured to fail"):
        await port.get_active_leads(Decimal("0.50"))


async def test_fail_on_call_raises_on_get_lead_score() -> None:
    port = InMemoryLeadSignalPort(fail_on_call=True)
    with pytest.raises(LeadSignalPortError, match="configured to fail"):
        await port.get_lead_score("lead-1001")


# ---------------------------------------------------------------------------
# 4. Value types / enums (I-01 Decimal, opaque handles)
# ---------------------------------------------------------------------------


def test_value_types_are_decimal_and_opaque() -> None:
    sig = LeadSignal(code=LeadSignalCode.SESSION_RECENCY, weight=Decimal("0.5"))
    assert sig.detail == ""  # default
    lead = ScoredLead(
        lead_id="l1",
        cohort="coh",
        score=Decimal("0.6"),
        band=LeadScoreBand.WARM,
        stage=LeadStage.ONBOARDING,
    )
    assert isinstance(lead.score, Decimal)
    ls = LeadScore(
        lead_id="l1",
        cohort="coh",
        score=Decimal("0.6"),
        band=LeadScoreBand.WARM,
        stage=LeadStage.ONBOARDING,
    )
    assert ls.signals == ()  # default empty


def test_enum_values() -> None:
    assert LeadScoreBand.COLD.value == "COLD"
    assert LeadScoreBand.WARM.value == "WARM"
    assert LeadScoreBand.HOT.value == "HOT"
    assert LeadStage.SIGNUP.value == "SIGNUP"
    assert LeadStage.ONBOARDING.value == "ONBOARDING"
    assert LeadStage.ACTIVATED.value == "ACTIVATED"
    assert LeadStage.ACTIVE.value == "ACTIVE"
    assert LeadSignalCode.SIGNUP_COMPLETED.value == "SIGNUP_COMPLETED"
    assert LeadSignalCode.PROFILE_COMPLETION.value == "PROFILE_COMPLETION"
    assert LeadSignalCode.ONBOARDING_PROGRESS.value == "ONBOARDING_PROGRESS"
    assert LeadSignalCode.FEATURE_ENGAGEMENT.value == "FEATURE_ENGAGEMENT"
    assert LeadSignalCode.SESSION_RECENCY.value == "SESSION_RECENCY"


def test_error_hierarchy() -> None:
    assert issubclass(LeadNotFound, LeadSignalPortError)
    assert issubclass(LeadSignalPortError, Exception)


# ---------------------------------------------------------------------------
# 5. INVARIANT: the port is READ-ONLY — no contact/outreach/nurture/write method
# ---------------------------------------------------------------------------


def test_port_is_read_only_no_mutating_methods() -> None:
    """LeadSignalPort exposes ONLY the two reads — no contact/outreach/nurture/write op.

    This is the contract-level enforcement of the agent's read-only invariant: a mutating
    op cannot be reached because no such method exists on the port at all.
    """
    public = {
        n
        for n, _ in inspect.getmembers(LeadSignalPort, inspect.isfunction)
        if not n.startswith("_")
    }
    assert public == {"get_active_leads", "get_lead_score"}
    forbidden = ("contact", "outreach", "nurture", "email", "send", "write", "update", "set_")
    for name in public:
        assert not any(tok in name.lower() for tok in forbidden), name


def test_abstract_port_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        LeadSignalPort()  # type: ignore[abstract]
