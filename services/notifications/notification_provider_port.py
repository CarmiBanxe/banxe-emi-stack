"""notification_provider_port.py — NotificationProviderPort: external multi-channel provider integration contract.

Referenced ADRs:
  ADR-021  PII routing (correlation_id / dedupe_key stored; raw payload scrubbed before storage)
  ADR-027  audit trail (guardian_audit_events; one row per channel attempt; retention >= 5 years)

WHY THIS FILE EXISTS
--------------------
The banxe-emi-stack must dispatch transactional and operational notifications
across multiple real-time delivery channels (Telegram, mobile push, email, SMS,
in-app) through one or more external providers.  This port isolates the domain
from any single provider SDK so that adapters can be swapped, multi-homed, or
circuit-broken without touching application or orchestration logic.

SEPARATION FROM notification_port.py (NotificationPort Protocol)
-----------------------------------------------------------------
notification_port.py defines NotificationPort, which governs the
application-facing, single-channel, Protocol-based interface used by internal
services (payment events, KYC lifecycle, compliance alerts).  It models one
request -> one result and is synchronous/Protocol-duck-typed.

This file defines NotificationProviderPort, which owns provider-facing I/O:
  send / is_channel_available

The two ports address different bounded contexts and MUST NOT be merged:

  NotificationPort     — application layer → adapter (one channel, one event)
  NotificationProviderPort — adapter → external provider (multi-channel fan-out,
                             dedupe, circuit-breaker, audit, severity routing)

Merging them would collapse the provider-integration boundary into the
application boundary, breaking hexagonal isolation and making it impossible to
swap or multi-home providers without touching orchestration code.

CONFORMANCE TEST SUITE
-----------------------
Nine conformance tests (IDs 1-9) per CONTRACT SPEC 2026-06-06 enforce the
behavioural contract documented on each method and exception class below.
(SPEC date: 2026-06-06.)

FUTURE WORK (out of scope here)
--------------------------------
- Adapter implementations (TelegramAdapter, FCMAdapter, SendGridProviderAdapter, TwilioAdapter)
- Circuit-breaker wiring (SPEC #6 @banxe/circuit-breaker)
- DLQ / backoff infrastructure for RateLimited (test 8)
- guardian_audit_events schema migration (ADR-027 §3)
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


class NotificationChannel(StrEnum):
    """Delivery channel supported by the provider-facing port.

    Values are lowercase strings suitable for use as database discriminators
    and JSON payloads.  Ordered here by approximate user-visibility priority.

    Conformance test 1 verifies that all five members are present and that
    their string values match exactly the literals below.
    """

    TELEGRAM = "telegram"
    MOBILE_PUSH = "mobile_push"
    EMAIL = "email"
    SMS = "sms"
    IN_APP = "in_app"


class Severity(StrEnum):
    """Message severity level; governs channel-routing and opt-out override.

    CRITICAL severity MUST attempt ALL available channels regardless of
    recipient channel_preferences (conformance test 3).  All other severity
    levels respect channel_preferences and opt-out flags.

    Conformance test 1 verifies that all four members are present and that
    their string values match exactly the literals below.
    """

    INFO = "info"
    WARN = "warn"
    ALERT = "alert"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Value objects  (frozen=True — immutable after construction)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Recipient:
    """Identifies the target user and their preferred delivery channels.

    channel_preferences expresses the ordered list of channels the user has
    enabled.  An empty list means the user has opted out of all non-critical
    delivery.  Adapters MUST respect this list for non-CRITICAL messages and
    MUST override it (attempt all available channels) for CRITICAL messages
    (conformance test 3).

    Required fields only; no defaulted fields.
    """

    user_id: str
    channel_preferences: list[NotificationChannel]


@dataclass(frozen=True)
class NotificationMessage:
    """Immutable value object describing a single notification to be delivered.

    Required fields (no defaults):
      severity        — governs routing and opt-out override (see Severity).
      subject         — short summary line; used as email subject / push title.
      body            — full message body; MUST NOT be empty (conformance test 5:
                        empty body raises ValidationError before any provider
                        call is made).
      correlation_id  — links this notification to the originating business
                        event; stored in guardian_audit_events (ADR-027).
      dedupe_key      — idempotency key; within a 24-hour window a second send
                        with the same dedupe_key MUST return a DeliveryResult
                        with deduped=True and MUST NOT re-deliver (conformance
                        test 2).

    Optional fields (with defaults):
      template        — provider-side template identifier; if supplied, the
                        provider renders body from template+data instead of
                        sending body verbatim.
      data            — arbitrary key-value payload merged into template
                        rendering; MUST be scrubbed of PII before storage
                        per ADR-021.
    """

    severity: Severity
    subject: str
    body: str
    correlation_id: str
    dedupe_key: str
    template: str | None = None
    data: dict[str, Any] | None = None


@dataclass(frozen=True)
class DeliveryResult:
    """Result of a single channel delivery attempt.

    send() returns one DeliveryResult per attempted channel so the caller can
    inspect per-channel success, failure, and deduplication outcomes
    (conformance test 4: partial delivery returns a mixed list).

    Required fields (no defaults):
      channel    — which channel this result describes.
      delivered  — True if the provider accepted the message for delivery.
      deduped    — True if the dedupe_key was already seen within the 24-hour
                   window; in this case delivered is False and no provider call
                   was made (conformance test 2).

    Optional fields (with defaults):
      provider_message_id — opaque provider-assigned identifier; present when
                            delivered=True; stored in guardian_audit_events
                            (ADR-027) for delivery reconciliation.
      error               — human-readable failure reason; present when
                            delivered=False and deduped=False.
    """

    channel: NotificationChannel
    delivered: bool
    deduped: bool
    provider_message_id: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Error hierarchy
# (all carry correlation_id + dedupe_key; persist to guardian_audit_events
#  per ADR-027 before re-raising)
# ---------------------------------------------------------------------------


class NotificationError(Exception):
    """Base for all provider-port errors.

    Every subclass MUST carry both correlation_id and dedupe_key so the
    adapter can write exactly one guardian_audit_events row per failed channel
    attempt before re-raising (ADR-027).

    Keyword-only arguments enforce that callers always supply both identifiers
    explicitly (mirrors KYCProviderError pattern).
    """

    def __init__(self, message: str, *, correlation_id: str, dedupe_key: str) -> None:
        super().__init__(message)
        self.correlation_id: str = correlation_id
        self.dedupe_key: str = dedupe_key


class ValidationError(NotificationError):
    """Message failed structural validation before any provider call.

    Current triggers:
      - body is empty or whitespace-only (conformance test 5).
      - recipient.channel_preferences is empty and severity < CRITICAL.

    Caller action: fix the message at the call site; do not retry.
    No guardian_audit_events row is written because no provider interaction
    occurred.
    """


class ChannelUnavailable(NotificationError):
    """Provider for the requested channel is unreachable or returned a
    transient error (conformance test 6: is_channel_available returns False).

    Caller action: mark this channel as failed in the DeliveryResult; continue
    attempting remaining channels (partial delivery is still returned).
    Retry via circuit-breaker (SPEC #6 @banxe/circuit-breaker).

    guardian_audit_events row MUST be written with status=FAILED,
    correlation_id, and dedupe_key (ADR-027).
    """


class RecipientOptedOut(NotificationError):
    """User has disabled this channel (channel absent from channel_preferences
    or explicit provider-level suppression list).

    Behaviour by severity:
      - Non-CRITICAL: channel is skipped; DeliveryResult.delivered=False,
        error='opted_out' (conformance test 7).
      - CRITICAL: opt-out is OVERRIDDEN; delivery is attempted on all
        available channels regardless of preferences (conformance test 3).

    Caller action: do not retry for non-critical; for critical, adapter
    suppresses this exception and proceeds with delivery.
    """


class RateLimited(NotificationError):
    """Provider has throttled the request for this channel.

    Caller action: enqueue the message for delayed retry with exponential
    backoff.  Do not drop the message.  Write a guardian_audit_events row
    with status=QUEUED and retry_count (ADR-027) (conformance test 8).
    """


class DedupeHit(NotificationError):
    """dedupe_key was already delivered within the 24-hour idempotency window.

    This is raised ONLY when the caller explicitly needs to distinguish a
    dedupe hit from a genuine failure.  Most callers should inspect
    DeliveryResult.deduped instead of catching this exception (conformance
    test 2).

    When raised, the corresponding DeliveryResult has deduped=True,
    delivered=False, and no provider call was made.
    """


# ---------------------------------------------------------------------------
# Abstract port
# ---------------------------------------------------------------------------


class NotificationProviderPort(abc.ABC):
    """Abstract contract for external multi-channel notification provider.

    Conformance rules (enforced by the 9-test conformance suite,
    CONTRACT SPEC 2026-06-06):

    Delivery guarantee:
      at-least-once delivery per channel; callers are responsible for
      idempotent consumers.

    Idempotency (ADR-027):
      send() is idempotent per dedupe_key within a 24-hour sliding window
      (conformance test 2).  A second send() with the same dedupe_key returns
      DeliveryResult(delivered=False, deduped=True) without contacting the
      provider.

    Severity routing:
      CRITICAL messages MUST attempt ALL available channels regardless of
      recipient.channel_preferences (conformance test 3).
      Non-CRITICAL messages MUST respect channel_preferences.

    Audit (ADR-027):
      Every channel attempt MUST emit exactly one guardian_audit_events row
      containing: correlation_id, dedupe_key, user_id, channel, severity,
      delivered, deduped, provider_message_id, timestamp_utc.
      Retention >= 5 years (AMLD5 / FCA SYSC).
    """

    @abstractmethod
    async def send(
        self,
        recipient: Recipient,
        message: NotificationMessage,
    ) -> list[DeliveryResult]:
        """Dispatch a notification to all applicable channels for recipient.

        Delivery semantics:
          - at-least-once; idempotent per dedupe_key within a 24-hour window
            (conformance test 2: second call with same dedupe_key returns
            DeliveryResult(delivered=False, deduped=True) without a provider
            call).
          - Routes by recipient.channel_preferences for non-CRITICAL messages.
          - For CRITICAL severity, attempts ALL channels for which
            is_channel_available() returns True, ignoring channel_preferences
            and opt-out flags (conformance test 3).
          - Returns one DeliveryResult per attempted channel; partial delivery
            (some channels failed, others succeeded) is surfaced via a mixed
            list — callers MUST NOT assume all-or-nothing (conformance test 4).

        Validation (pre-provider):
          - Empty or whitespace-only body raises ValidationError before any
            provider call is made (conformance test 5).

        Opt-out handling:
          - RecipientOptedOut: channel is skipped for non-critical messages;
            delivery proceeds for CRITICAL (conformance test 7).

        Rate-limiting:
          - RateLimited: message is queued for retry with exponential backoff;
            current attempt returns delivered=False in the DeliveryResult
            (conformance test 8).

        Audit:
          - Emits exactly one guardian_audit_events row per attempted channel
            containing correlation_id, dedupe_key, user_id, channel,
            delivered, deduped, provider_message_id, timestamp_utc (ADR-027)
            (conformance test 9).

        Args:
            recipient: target user with channel preferences.
            message:   immutable notification payload including severity,
                       correlation_id, and dedupe_key.

        Returns:
            List of DeliveryResult, one per attempted channel.

        Raises:
            ValidationError:    body is empty (conformance test 5).
            ChannelUnavailable: raised per-channel; other channels still
                                attempted; included as error in DeliveryResult.
        """
        ...

    @abstractmethod
    async def is_channel_available(self, channel: NotificationChannel) -> bool:
        """Return True if the provider for channel is currently reachable.

        Read-only health probe; MUST NOT trigger any state change or audit row.
        Used by the circuit-breaker (SPEC #6 @banxe/circuit-breaker) and by
        send() to determine which channels to attempt for CRITICAL messages.

        Returns False if the provider is down, misconfigured, or rate-limiting
        at the account level (conformance test 6).

        Args:
            channel: the channel whose provider to probe.

        Returns:
            True if the provider accepted a health-check probe; False otherwise.
        """
        ...
