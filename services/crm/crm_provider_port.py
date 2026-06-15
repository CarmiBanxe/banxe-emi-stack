"""crm_provider_port.py — CRMProviderPort: external CRM/referral provider integration contract.

SPEC #6 CRMPort CONTRACT / C10 referral/CRM capability.

Referenced ADRs:
  ADR-021  CRMPort (port naming + boundary)
  ADR-027  audit trail (guardian_audit_events; one row per mutating operation; retention >= 5 years)
  R-COMP-FCA-03  referral audit (RISK_REGISTER 2026-05-22)

WHY THIS FILE EXISTS
--------------------
The banxe-emi-stack must integrate with a CRM/referral backend (initially the
legacy banxe-referrers service, per SPEC #6) for referral registration, code
resolution, user profile reads, and tier management.  This port isolates the
domain from any single CRM implementation so adapters can be swapped or
extended without touching application or compliance logic.

SEPARATION FROM services/referral/* (legacy)
--------------------------------------------
services/referral/* owns legacy referral domain logic and is explicitly
UNTOUCHED by this contract.  CRMProviderPort provides a clean provider-facing
boundary for NEW capability C10 (referral / CRM) per NEW-PROJECT-PRIORITY-MAP.
The ReferralCRMAdapter (Terminal B, out of scope here) wires the two together.

CONFORMANCE TEST SUITE
-----------------------
Seven conformance tests (IDs 1-7) per CONTRACT SPEC 2026-06-06 enforce the
behavioural contract documented on each method and exception class below.

  1. register_referral(valid pair)         -> accepted=True
  2. register_referral same pair twice     -> accepted=False, reason="already_registered"
  3. register_referral self               -> accepted=False, reason="self_referral"
  4. resolve_referral_code(known)         -> owning CRMUserId; unknown -> None
  5. get_user(known)                      -> CRMUser; unknown -> None
  6. update_user_tier(new tier)           -> applied; same tier -> no-op success
  7. every mutating op emits one guardian_audit_events row with correlation_id

FUTURE WORK (out of scope here)
--------------------------------
- ReferralCRMAdapter implementation (Terminal B, banxe-referrers wiring)
- guardian_audit_events schema migration (ADR-027 §3)
- Circuit-breaker wiring (SPEC #6 @banxe/circuit-breaker)
"""

from __future__ import annotations

import abc
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

CRMUserId = str
ReferralCode = str

# ---------------------------------------------------------------------------
# Value objects  (frozen=True — immutable after construction)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReferralEvent:
    """Immutable value object describing a referral registration event.

    Required fields (no defaults):
      referrer       — CRM user ID of the referrer (must not equal referee).
      referee        — CRM user ID of the newly-referred user.
      code           — referral code used; keyed to the referrer.
      occurred_at    — ISO-8601 UTC timestamp string when the referral occurred.
      correlation_id — links this event to the originating business flow;
                       stored in guardian_audit_events (ADR-027 / R-COMP-FCA-03).

    Optional fields:
      metadata       — arbitrary provider-specific context; scrubbed of PII
                       before storage per ADR-021.
    """

    referrer: CRMUserId
    referee: CRMUserId
    code: ReferralCode
    occurred_at: str
    correlation_id: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class CRMUser:
    """Snapshot of a user profile returned by the CRM provider.

    Required fields:
      user_id — canonical CRM user identifier.

    Optional fields:
      tier       — user's current tier label (e.g. "basic", "premium").
      attributes — provider-specific key-value attributes; scrubbed of PII
                   before storage per ADR-021.
    """

    user_id: CRMUserId
    tier: str | None = None
    attributes: dict[str, Any] | None = None


@dataclass(frozen=True)
class RegisterReferralResult:
    """Result of a register_referral call.

    accepted=True means the referral was recorded for the first time.
    accepted=False with a reason indicates why it was rejected (idempotent
    duplicate or self-referral — see AlreadyRegistered and SelfReferral).

    Fields:
      accepted — True if referral was newly registered; False if rejected.
      reason   — human-readable rejection code; present only when accepted=False.
                 Canonical values: "already_registered", "self_referral".
    """

    accepted: bool
    reason: str | None = None


# ---------------------------------------------------------------------------
# Error hierarchy
# (all carry correlation_id; adapters persist to guardian_audit_events
#  per ADR-027 / R-COMP-FCA-03 before re-raising)
# ---------------------------------------------------------------------------


class CRMProviderError(Exception):
    """Base for all CRM provider-port errors.

    Every subclass MUST carry correlation_id so the adapter can write exactly
    one guardian_audit_events row per failed operation before re-raising
    (ADR-027 / R-COMP-FCA-03).

    Keyword-only argument enforces that callers always supply the identifier
    explicitly (mirrors KYCProviderError pattern).
    """

    def __init__(self, message: str, *, correlation_id: str) -> None:
        super().__init__(message)
        self.correlation_id: str = correlation_id


class ValidationError(CRMProviderError):
    """Input failed structural validation before any provider call.

    Current triggers:
      - Empty or whitespace-only user_id or code.
      - Malformed referral code rejected by the provider.

    Caller action: fix and resubmit; do not retry as-is.
    No guardian_audit_events row is written because no provider interaction
    occurred (conformance test: validation errors are pre-flight).
    """


class SelfReferral(CRMProviderError):
    """referrer == referee: a user attempted to refer themselves.

    This is a fraud signal and MUST be surfaced to AML analysis.
    Caller action: reject; do not retry; flag as potential fraud.
    Adapter MUST log the blocked attempt to guardian_audit_events.

    register_referral returns RegisterReferralResult(accepted=False,
    reason="self_referral") in normal flow.  This exception is raised ONLY
    when the caller needs to distinguish self-referral from other rejections
    at the exception level (conformance test 3).
    """


class AlreadyRegistered(CRMProviderError):
    """The referee already has a registered referrer.

    Idempotency rule: a referee can only be registered once.
    register_referral returns RegisterReferralResult(accepted=False,
    reason="already_registered") in normal flow.  This exception is raised
    ONLY when the caller needs to distinguish a duplicate registration from a
    genuine processing failure (conformance test 2).

    Caller action: reject; not retryable.
    """


class UnknownReferralCode(CRMProviderError):
    """The referral code does not resolve to any CRM user.

    resolve_referral_code returns None in normal flow.  This exception is
    raised ONLY when the caller treats an unresolvable code as a hard error
    (e.g., during registration pre-validation).

    Caller action: surface to user; do not retry with the same code
    (conformance test 4).
    """


# ---------------------------------------------------------------------------
# Abstract port
# ---------------------------------------------------------------------------


class CRMProviderPort(abc.ABC):
    """Abstract contract for external CRM/referral provider integration.

    Conformance rules (enforced by the 7-test conformance suite,
    CONTRACT SPEC 2026-06-06):

    Idempotency:
      register_referral — idempotent per (referrer, referee) pair; a referee
                          can only be registered once (conformance tests 1-3).
      update_user_tier  — idempotent per (user_id, tier); re-applying the
                          same tier is a no-op success (conformance test 6).

    Fraud guard:
      Self-referral (referrer == referee) is blocked unconditionally and
      surfaced as a fraud signal via AML analysis (conformance test 3).

    Read-only operations:
      resolve_referral_code and get_user MUST NOT emit audit rows and MUST NOT
      trigger any state change (conformance tests 4-5).

    Audit (ADR-027 / R-COMP-FCA-03):
      Every mutating operation (register_referral, update_user_tier) MUST
      emit exactly one guardian_audit_events row containing:
      correlation_id, referrer, referee, code, tier, accepted, reason,
      timestamp_utc.  Referral events retained for AML fraud analysis;
      tier changes for FCA evidence.  Retention >= 5 years (conformance test 7).
    """

    @abstractmethod
    async def register_referral(
        self,
        event: ReferralEvent,
    ) -> RegisterReferralResult:
        """Register a referral event for the (referrer, referee) pair.

        Idempotency contract:
          - First call with a novel (referrer, referee) pair MUST record the
            referral and return RegisterReferralResult(accepted=True)
            (conformance test 1).
          - A second call with the same (referrer, referee) pair MUST return
            RegisterReferralResult(accepted=False, reason="already_registered")
            without re-applying the registration (conformance test 2).
          - Self-referral (event.referrer == event.referee) MUST return
            RegisterReferralResult(accepted=False, reason="self_referral") and
            MUST emit a guardian_audit_events row flagged as a fraud signal
            (conformance test 3).

        Audit (ADR-027 / R-COMP-FCA-03):
          Emits exactly one guardian_audit_events row per call containing
          event.correlation_id, referrer, referee, code, accepted, reason,
          and timestamp_utc (conformance test 7).

        Args:
            event: immutable referral event value object including correlation_id.

        Returns:
            RegisterReferralResult with accepted=True on first registration;
            accepted=False with reason on duplicate or self-referral.

        Raises:
            ValidationError: empty user_id or code (pre-flight; no audit row).
        """
        ...

    @abstractmethod
    async def resolve_referral_code(
        self,
        code: ReferralCode,
    ) -> CRMUserId | None:
        """Resolve a referral code to its owning CRM user ID.

        Read-only; MUST NOT trigger any state change or emit an audit row
        (conformance test 4).

        Args:
            code: referral code to resolve.

        Returns:
            CRMUserId of the code owner, or None if the code is unknown
            (conformance test 4: unknown code -> None).

        Raises:
            ValidationError: empty or malformed code.
        """
        ...

    @abstractmethod
    async def get_user(
        self,
        user_id: CRMUserId,
    ) -> CRMUser | None:
        """Return the CRM user profile for user_id.

        Read-only; MUST NOT trigger any state change or emit an audit row
        (conformance test 5).

        Args:
            user_id: CRM user identifier.

        Returns:
            CRMUser if the user exists, or None if not found
            (conformance test 5: unknown user_id -> None).

        Raises:
            ValidationError: empty user_id.
        """
        ...

    @abstractmethod
    async def update_user_tier(
        self,
        user_id: CRMUserId,
        tier: str,
        correlation_id: str,
    ) -> None:
        """Apply a tier change to a CRM user.

        Idempotency contract:
          Re-applying the same tier to the same user_id is a no-op success;
          no second guardian_audit_events row is written for a no-op call
          (conformance test 6).

        Audit (ADR-027):
          Emits exactly one guardian_audit_events row per non-no-op call
          containing correlation_id, user_id, tier, and timestamp_utc
          (conformance test 7).

        Args:
            user_id:        CRM user identifier.
            tier:           new tier label to apply (e.g. "basic", "premium").
            correlation_id: links this change to the originating business event.

        Raises:
            ValidationError: empty user_id or tier.
        """
        ...
