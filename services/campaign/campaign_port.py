"""campaign_port.py — CampaignPort: marketing-campaign orchestration contract.

ORG-STRUCTURE §2.8.2 Marketing & Growth — `CampaignAgent` (L2 Review, gate MLRO
for financial promotions, Listmonk AGPL). This port isolates the domain from any
single campaign/email engine (Listmonk, etc.) so adapters can be swapped without
touching application logic.

Referenced canon:
  ORG §2.8.2 COBS 4  financial-promotion review — AI may DRAFT but NEVER auto-publish
  ADR-049 §D2/§D3    mask gate-chain + scope allow-list
  ADR-021 / R-SEC    opaque metadata only — never marketing content or recipient PII

THE PUBLISH BOUNDARY (COBS 4 — enforced in code)
------------------------------------------------
``prepare_campaign`` is a free DRAFT operation: an AI may compose/store a campaign
draft at will (no human gate). ``publish_campaign`` is the regulated send path: a
campaign that PUBLISHES financial-promotion content can NEVER be issued
autonomously — the port REQUIRES a valid :class:`MlroReviewToken` and raises
:class:`MlroReviewRequired` without one. This is defence-in-depth: the
:class:`~services.agents.campaign_agent.CampaignAgent` mask gates the token at the
governance layer (forced step-up to MLRO), and the port re-checks at the I/O seam.

SEPARATION FROM services/referral/campaign_manager.py
-----------------------------------------------------
``referral/campaign_manager.py`` owns the *referral-reward* campaign lifecycle
(DRAFT→ACTIVE→PAUSED→ENDED, budget tracking). This port owns *marketing
email/push* campaign orchestration (draft → MLRO-gated publish). They are
different bounded contexts and MUST NOT be merged; this port does not touch the
referral domain. A production adapter would delegate the publish path to Listmonk
(and may reuse the referral lifecycle for reward campaigns) — that real
integration is a LATER sprint (I-10: no fake integrations now). This module ships
the contract + an in-memory double for unit tests only.

FUTURE WORK (out of scope here)
-------------------------------
- Listmonk adapter (ListmonkCampaignPort), opt-in/consent + unsubscribe (UK GDPR)
- Real MLRO review-token issuance/verification service (Guardian sign-off)
"""

from __future__ import annotations

import abc
from abc import abstractmethod
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class CampaignChannel(StrEnum):
    """Delivery channel for a marketing campaign."""

    EMAIL = "email"
    PUSH = "push"


class CampaignStatus(StrEnum):
    """Marketing-campaign lifecycle status (draft → published)."""

    DRAFT = "draft"
    PUBLISHED = "published"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CampaignDraft:
    """A composed-but-unsent marketing campaign.

    ``subject``/``body`` are the marketing *content*; ``is_financial_promotion``
    marks content involving financial products (COBS 4 scope). Content and any
    recipient PII ride on this draft straight to the port — they are NEVER part of
    a lineage record (R-SEC); only ``campaign_id``/``segment`` are loggable.
    """

    campaign_id: str
    name: str
    segment: str
    channel: CampaignChannel
    subject: str
    body: str
    is_financial_promotion: bool
    estimated_reach: int
    budget: Decimal = Decimal("0")


@dataclass(frozen=True)
class MlroReviewToken:
    """Evidence of MLRO sign-off on a financial-promotion campaign (COBS 4).

    A token is *valid* only when it carries a non-empty ``token_id`` and reviewer
    and is bound to the exact ``campaign_id`` being published — a token issued for
    one campaign can never authorise another.
    """

    token_id: str
    campaign_id: str
    reviewed_by: str

    def is_valid_for(self, campaign_id: str) -> bool:
        return bool(self.token_id) and bool(self.reviewed_by) and self.campaign_id == campaign_id


@dataclass(frozen=True)
class PublishedCampaign:
    """Result of a successful ``publish_campaign`` — the regulated send receipt."""

    campaign_id: str
    status: CampaignStatus
    channel: CampaignChannel
    recipients: int
    reviewed_by: str


# ---------------------------------------------------------------------------
# Error hierarchy (all carry correlation_id for the audit trail)
# ---------------------------------------------------------------------------


class CampaignPortError(Exception):
    """Base for all campaign-port errors. Carries ``correlation_id`` so the adapter
    can write an audit row before re-raising."""

    def __init__(self, message: str, *, correlation_id: str) -> None:
        super().__init__(message)
        self.correlation_id: str = correlation_id


class CampaignNotFound(CampaignPortError):
    """campaign_id not present in the store."""


class MlroReviewRequired(CampaignPortError):
    """publish_campaign was called for a financial promotion without a valid MLRO
    review token. COBS 4: AI may draft but NEVER auto-publish (caller action: route
    to MLRO for sign-off; do not retry without a bound, valid token)."""


class ProviderUnavailable(CampaignPortError):
    """The campaign engine is down or returned a transient error (caller retries)."""


# ---------------------------------------------------------------------------
# Abstract port
# ---------------------------------------------------------------------------


class CampaignPort(abc.ABC):
    """Abstract contract for marketing email/push campaign orchestration.

    Boundary (COBS 4): ``prepare_campaign`` is a free draft op; ``publish_campaign``
    of a financial promotion is NEVER autonomous and requires a valid
    :class:`MlroReviewToken`. ``list_campaigns`` is a read.
    """

    @abstractmethod
    async def prepare_campaign(self, draft: CampaignDraft) -> CampaignDraft:
        """Compose/store a campaign in DRAFT status. Free — no human gate (COBS 4:
        AI may draft). Idempotent per ``campaign_id``: a re-prepare replaces the
        stored draft and never transitions status away from DRAFT."""
        ...

    @abstractmethod
    async def publish_campaign(
        self, draft: CampaignDraft, mlro_token: MlroReviewToken
    ) -> PublishedCampaign:
        """Issue/send the campaign — the regulated path.

        COBS 4: a financial-promotion publish requires a valid MLRO review token
        bound to ``draft.campaign_id``. An absent/invalid token MUST raise
        :class:`MlroReviewRequired` and send nothing.

        Raises:
            MlroReviewRequired: financial promotion without a valid bound token.
            CampaignNotFound: campaign_id was never prepared.
            ProviderUnavailable: transient engine error; caller should retry.
        """
        ...

    @abstractmethod
    async def list_campaigns(self) -> tuple[CampaignDraft, ...]:
        """Return all known campaign drafts (read-only; safe to poll)."""
        ...


# ---------------------------------------------------------------------------
# In-memory implementation (unit-test double — I-10: no real Listmonk yet)
# ---------------------------------------------------------------------------


class InMemoryCampaignPort(CampaignPort):
    """In-memory :class:`CampaignPort` for unit tests. Holds drafts in a dict and
    enforces the same COBS 4 publish-token rule the real adapter must (defence in
    depth alongside the agent's governance gate)."""

    def __init__(self) -> None:
        self._drafts: dict[str, CampaignDraft] = {}
        self._published: dict[str, PublishedCampaign] = {}

    async def prepare_campaign(self, draft: CampaignDraft) -> CampaignDraft:
        self._drafts[draft.campaign_id] = draft
        return draft

    async def publish_campaign(
        self, draft: CampaignDraft, mlro_token: MlroReviewToken
    ) -> PublishedCampaign:
        if draft.campaign_id not in self._drafts:
            raise CampaignNotFound(
                f"Campaign not prepared: {draft.campaign_id}",
                correlation_id=draft.campaign_id,
            )
        # COBS 4 — a financial-promotion publish is NEVER autonomous: a valid,
        # campaign-bound MLRO token is mandatory or nothing is sent.
        if draft.is_financial_promotion and not mlro_token.is_valid_for(draft.campaign_id):
            raise MlroReviewRequired(
                "Financial promotion requires a valid MLRO review token before publish "
                f"(campaign {draft.campaign_id}).",
                correlation_id=draft.campaign_id,
            )
        published = PublishedCampaign(
            campaign_id=draft.campaign_id,
            status=CampaignStatus.PUBLISHED,
            channel=draft.channel,
            recipients=draft.estimated_reach,
            reviewed_by=mlro_token.reviewed_by,
        )
        self._published[draft.campaign_id] = published
        self._drafts[draft.campaign_id] = replace(draft)
        return published

    async def list_campaigns(self) -> tuple[CampaignDraft, ...]:
        return tuple(self._drafts.values())


__all__ = [
    "CampaignChannel",
    "CampaignDraft",
    "CampaignNotFound",
    "CampaignPort",
    "CampaignPortError",
    "CampaignStatus",
    "InMemoryCampaignPort",
    "MlroReviewRequired",
    "MlroReviewToken",
    "ProviderUnavailable",
    "PublishedCampaign",
]
