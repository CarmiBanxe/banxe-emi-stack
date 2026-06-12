"""Tests for the CampaignPort contract + InMemoryCampaignPort
(services/campaign/campaign_port.py).

Covers the full surface for 100% coverage: prepare (free draft), the COBS 4
publish boundary (financial promo requires a valid, campaign-bound MLRO token —
MlroReviewRequired without one), non-financial publish, CampaignNotFound,
list_campaigns, the MlroReviewToken validity predicate, and the error hierarchy.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.campaign.campaign_port import (
    CampaignChannel,
    CampaignDraft,
    CampaignNotFound,
    CampaignPortError,
    CampaignStatus,
    InMemoryCampaignPort,
    MlroReviewRequired,
    MlroReviewToken,
    ProviderUnavailable,
    PublishedCampaign,
)


def make_draft(
    *,
    campaign_id: str = "camp-1",
    financial: bool = True,
    reach: int = 1000,
) -> CampaignDraft:
    return CampaignDraft(
        campaign_id=campaign_id,
        name="Summer Savings Boost",
        segment="active-uk",
        channel=CampaignChannel.EMAIL,
        subject="Earn 5% on your savings",
        body="Open a savings pot today and earn 5% AER.",
        is_financial_promotion=financial,
        estimated_reach=reach,
        budget=Decimal("250.00"),
    )


def make_token(*, campaign_id: str = "camp-1", token_id: str = "tok-1") -> MlroReviewToken:
    return MlroReviewToken(token_id=token_id, campaign_id=campaign_id, reviewed_by="mlro@banxe")


# ── prepare (free draft) ────────────────────────────────────────────────────────


async def test_prepare_stores_draft_and_returns_it():
    port = InMemoryCampaignPort()
    draft = make_draft()
    out = await port.prepare_campaign(draft)
    assert out == draft
    assert (await port.list_campaigns()) == (draft,)


# ── publish boundary (COBS 4) ────────────────────────────────────────────────────


async def test_publish_financial_promo_with_valid_token_sends():
    port = InMemoryCampaignPort()
    draft = make_draft(financial=True, reach=2500)
    await port.prepare_campaign(draft)
    published = await port.publish_campaign(draft, make_token())
    assert isinstance(published, PublishedCampaign)
    assert published.status is CampaignStatus.PUBLISHED
    assert published.recipients == 2500
    assert published.reviewed_by == "mlro@banxe"
    assert published.channel is CampaignChannel.EMAIL


async def test_publish_financial_promo_without_valid_token_raises():
    port = InMemoryCampaignPort()
    draft = make_draft(financial=True)
    await port.prepare_campaign(draft)
    # Token bound to a DIFFERENT campaign — never authorises this one.
    bad = MlroReviewToken(token_id="tok-x", campaign_id="other", reviewed_by="mlro@banxe")
    with pytest.raises(MlroReviewRequired) as exc:
        await port.publish_campaign(draft, bad)
    assert exc.value.correlation_id == "camp-1"


async def test_publish_non_financial_skips_token_gate():
    port = InMemoryCampaignPort()
    draft = make_draft(financial=False)
    await port.prepare_campaign(draft)
    # Non-financial: token gate does not apply (still carries reviewer metadata).
    published = await port.publish_campaign(draft, make_token())
    assert published.status is CampaignStatus.PUBLISHED


async def test_publish_unprepared_campaign_raises_not_found():
    port = InMemoryCampaignPort()
    draft = make_draft()
    with pytest.raises(CampaignNotFound):
        await port.publish_campaign(draft, make_token())


# ── list ─────────────────────────────────────────────────────────────────────────


async def test_list_campaigns_empty_then_populated():
    port = InMemoryCampaignPort()
    assert (await port.list_campaigns()) == ()
    await port.prepare_campaign(make_draft(campaign_id="a"))
    await port.prepare_campaign(make_draft(campaign_id="b"))
    ids = {c.campaign_id for c in await port.list_campaigns()}
    assert ids == {"a", "b"}


# ── MlroReviewToken predicate ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("token", "campaign_id", "expected"),
    [
        (MlroReviewToken("t", "camp-1", "mlro"), "camp-1", True),
        (MlroReviewToken("", "camp-1", "mlro"), "camp-1", False),  # empty token_id
        (MlroReviewToken("t", "camp-1", ""), "camp-1", False),  # empty reviewer
        (MlroReviewToken("t", "camp-1", "mlro"), "camp-2", False),  # bound elsewhere
    ],
)
def test_token_is_valid_for(token, campaign_id, expected):
    assert token.is_valid_for(campaign_id) is expected


# ── error hierarchy ──────────────────────────────────────────────────────────────


def test_error_hierarchy_and_correlation_id():
    err = ProviderUnavailable("engine down", correlation_id="corr-1")
    assert isinstance(err, CampaignPortError)
    assert err.correlation_id == "corr-1"
    assert issubclass(MlroReviewRequired, CampaignPortError)
    assert issubclass(CampaignNotFound, CampaignPortError)
