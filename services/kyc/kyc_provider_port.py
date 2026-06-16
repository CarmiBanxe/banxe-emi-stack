"""kyc_provider_port.py — KYCProviderPort: external KYC provider integration contract.

SPEC #8 KYCProviderPort / C5 KYC/AML capability.

Referenced ADRs:
  ADR-028  re-verification triggers (tier upgrade/downgrade lifecycle)
  ADR-034  webhook reliability (HMAC-first, DLQ, idempotency)
  ADR-021  PII routing (raw payload scrubbing before storage)
  ADR-027  audit trail (guardian_audit_events; retention ≥ 5 years)
  R-REG-02 regulatory reporting obligation (FCA MLR 2017 §18-27)

WHY THIS FILE EXISTS
--------------------
The banxe-emi-stack must integrate with one or more external KYC providers
(Sumsub, Onfido, etc.) for web-SDK session issuance, async status polling,
real-time webhook processing, and tier change requests.  This port isolates
the domain from any single provider SDK so that adapters can be swapped or
multi-homed without touching application logic.

SEPARATION FROM kyc_port.py (KYCWorkflowPort)
----------------------------------------------
This file defines KYCProviderPort, which owns provider-facing I/O:
  start_session / get_status / handle_webhook / change_level.

kyc_port.py defines KYCWorkflowPort, which governs internal workflow
orchestration (Ballerine, document review, EDD, MLRO sign-off).

These two ports address different bounded contexts and MUST NOT be merged.
Merging them would collapse the provider-integration boundary into the
internal workflow boundary, breaking hexagonal isolation and making it
impossible to swap providers without touching orchestration code.

FUTURE WORK (out of scope here)
--------------------------------
- Adapter implementations (SumsubAdapter, OnfidoAdapter)
- DLQ infrastructure and retry logic (ADR-034 §4)
- Conformance test suite (test IDs 1-11 per CONTRACT SPEC 2026-06-06)
"""

from __future__ import annotations

import abc
from abc import abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class KYCTier(StrEnum):
    """Regulatory verification tier.  Ordered by depth: NONE < BASIC < INTERMEDIATE < FULL."""

    NONE = "none"
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    FULL = "full"


class KYCStatus(StrEnum):
    """Canonical KYC lifecycle status as reported by the provider."""

    NOT_STARTED = "not_started"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVIEW = "review"
    EXPIRED = "expired"


# Alias kept readable at call-sites without exposing a bare str.
ProviderLevelId = str


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KYCSession:
    """Opaque session issued by the provider's web-SDK token endpoint.

    Every field is required; adapters MUST NOT emit a session with blank tokens.
    expires_at is an ISO-8601 UTC timestamp string (provider-formatted).
    """

    user_id: str
    access_token: str
    expires_at: str
    provider_level_id: ProviderLevelId
    correlation_id: str


@dataclass(frozen=True)
class KYCResult:
    """Snapshot of the user's KYC state as returned by the provider.

    raw: provider-verbatim payload kept for FCA Section 4 evidence; PII MUST
    be redacted by the adapter per ADR-021 before storage (field present here
    to carry the scrubbed payload, not to expose raw PII).
    reject_reasons: human-readable strings from the provider (non-PII).
    """

    user_id: str
    status: KYCStatus
    tier: KYCTier
    provider_level_id: ProviderLevelId
    reviewed_at: str | None = None
    reject_reasons: list[str] | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class WebhookOutcome:
    """Result of a single handle_webhook call.

    deduped=True means the event was already seen (idempotent replay); no
    state change was applied.  processed=True + deduped=False means the event
    was new and the status transition was persisted.
    """

    processed: bool
    deduped: bool
    user_id: str | None = None
    new_status: KYCStatus | None = None


# ---------------------------------------------------------------------------
# Error hierarchy (all carry correlation_id; persist to guardian_audit_events)
# ---------------------------------------------------------------------------


class KYCProviderError(Exception):
    """Base for all provider-port errors.

    Every subclass MUST carry correlation_id so the adapter can write a
    guardian_audit_events row before re-raising (ADR-027).
    """

    def __init__(self, message: str, *, correlation_id: str) -> None:
        super().__init__(message)
        self.correlation_id: str = correlation_id


class InvalidSignature(KYCProviderError):
    """Webhook HMAC verification failed.

    Caller action: reject the request; write audit row; never process the
    payload.  Repeated occurrences should be escalated as a possible attack.
    """


class UnknownUser(KYCProviderError):
    """user_id not recognised by the provider.

    Caller action: reject; this indicates a caller-side bug or stale reference.
    """


class ProviderUnavailable(KYCProviderError):
    """Provider API is down or returned a transient error.

    Caller action: retry via circuit-breaker (SPEC #6 @banxe/circuit-breaker).
    get_status continues to return the last-known KYCResult during outage.
    """


class TierDowngradeBlocked(KYCProviderError):
    """A regulatory rule forbids the requested tier downgrade.

    Caller action: do not retry; escalate to MLRO for manual review.
    Adapter MUST log the blocked attempt to guardian_audit_events.
    """


class WebhookReplayDetected(KYCProviderError):
    """Provider event id was already processed (idempotency guard).

    Adapter returns WebhookOutcome(processed=False, deduped=True) and raises
    this exception ONLY when the caller needs to distinguish replay from a
    genuine failure.  Most callers should inspect WebhookOutcome.deduped.
    """


# ---------------------------------------------------------------------------
# Abstract port
# ---------------------------------------------------------------------------


class KYCProviderPort(abc.ABC):
    """Abstract contract for external KYC provider integration.

    Conformance rules (enforced by the adapter conformance test suite,
    test IDs 1-11 per CONTRACT SPEC 2026-06-06):

    Audit (ADR-027 / R-REG-02):
      Every method MUST emit exactly one guardian_audit_events row containing:
      correlation_id, user_id, operation, status, tier, provider_level_id,
      http_status, timestamp_utc.  Retention >= 5 years (CASS 15 / AMLD).

    Idempotency:
      start_session  — idempotent per (user_id, tier) within token TTL.
      handle_webhook — idempotent per provider event id.
      change_level   — idempotent per (user_id, new_tier) until transition.

    Webhook reliability (ADR-034):
      handle_webhook verifies HMAC BEFORE any processing.
      On downstream failure: push to DLQ with retry counter; exponential
      backoff; after max retries alert MLRO.  Never silently drop a status
      change.
    """

    @abstractmethod
    async def start_session(
        self,
        user_id: str,
        tier: KYCTier,
        correlation_id: str,
    ) -> KYCSession:
        """Issue a provider web-SDK access token for the given tier.

        Idempotent: a second call with the same (user_id, tier) within the
        token TTL MUST return the same session (conformance test 2).

        Raises:
            UnknownUser: user_id not known to the provider.
            ProviderUnavailable: transient provider error; caller should retry.
        """
        ...

    @abstractmethod
    async def get_status(self, user_id: str) -> KYCResult:
        """Return the last-known KYC state for user_id.

        Read-only; safe to poll; MUST NOT trigger any state change (conformance
        test 3).  Returns the last-known result during provider outages.

        Raises:
            UnknownUser: user_id not found (conformance test 4).
        """
        ...

    @abstractmethod
    async def handle_webhook(
        self,
        payload: object,
        signature: str,
    ) -> WebhookOutcome:
        """Process a provider-initiated status-update webhook.

        Security contract:
          HMAC signature MUST be verified before ANY processing (conformance
          test 6).  Invalid signature -> raise InvalidSignature; audit; return
          without touching state.

        Idempotency contract:
          Duplicate event id -> return WebhookOutcome(processed=False,
          deduped=True); do NOT re-apply the state transition (conformance
          test 7).

        Reliability contract (ADR-034):
          Downstream failure during processing -> push to DLQ with retry
          counter; do not raise to the HTTP layer (conformance test 8).

        Raises:
            InvalidSignature: HMAC mismatch (conformance test 6).
        """
        ...

    @abstractmethod
    async def change_level(
        self,
        user_id: str,
        new_tier: KYCTier,
        correlation_id: str,
    ) -> KYCResult:
        """Request a tier upgrade or downgrade for user_id.

        Upgrade triggers re-verification per ADR-028 (conformance test 9).
        Regulatory-forbidden downgrade MUST raise TierDowngradeBlocked and
        log an MLRO escalation event (conformance test 10).

        Idempotent: repeated call with the same (user_id, new_tier) before the
        status actually transitions returns the current KYCResult unchanged.

        Raises:
            TierDowngradeBlocked: regulatory rule forbids this downgrade.
            UnknownUser: user_id not found.
            ProviderUnavailable: transient provider error.
        """
        ...
