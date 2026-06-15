"""card_port.py — CardPort: governed card-operations CONTRACT (C22).

ADR-053 D3/D4 Cards mask (C22) / SPEC #15 Card issuance (CardPort + Paymentology).

Referenced ADRs / specs:
  ADR-053  Client-facing mask catalogue extensibility; the Cards (C22) mask and
           the mask <-> domain-agent governance boundary. CardPort is the
           CONTRACT port the Cards mask `scope` allow-lists (D3 step 1, D4).
  ADR-049  Intent-layer client-facing agent masks (the §D2 gate chain, §D3 mask
           fields, §D4 thresholds + biometric step-up the Cards mask reuses).
  ADR-046  Decision Lineage Schema — one AgentDecisionRecord per masked action.
  ADR-047  AI Cost Governance Policy — per-request / per-window cost caps.
  ADR-016  AI-plane PII/AML routing — compliance_gate overlay for card ops.
  ADR-027  Audit trail (guardian_audit_events; one row per mutating op; >= 5y).
  SPEC #15 Card issuance group (CardPort + Paymentology); PCI-DSS scope review.
  R-SEC-PCI-01  PAN handling: PAN never stored; tokenised; PCI-DSS scope minimised.

WHY THIS FILE EXISTS
--------------------
ADR-053 makes the ADR-049 client-facing mask catalogue extensible and adds the
Cards (C22) mask as its first new entry. A mask may only scope operations on a
real hexagonal CONTRACT port (ADR-053 D1 step 2: "no mask may scope a capability
that has no port"). CardPort is that boundary object: the Cards mask `scope`
allow-lists exactly the governed card operations defined here, and nothing
outside this port is reachable through the mask.

CardPort exposes ONLY the ADR-053 D4 allow-list — the governed client-surface
operations:
  reads      : read_card, read_limits
  protective : freeze, block, unfreeze   (AUTO-with-cap; low-regret)
  value/credit: issue_card, change_limit (REVIEW + biometric step-up)

GOVERNANCE BOUNDARY (ADR-053 D2 — canonical)
--------------------------------------------
CardPort is the boundary where governance (in front) meets domain implementation
(behind). The mask-governed client-facing CardsAgent sits IN FRONT of this port
and calls it through the full ADR-049 §D2 chain; the existing domain
service-agent `services/card_issuing/card_agent.py` (and its issuer / lifecycle /
spend-control / transaction collaborators) sits BEHIND this port as the ADAPTER,
untouched. A client intent MUST NOT reach the domain agent directly.

This file authors NO adapter and touches NO existing card_issuing logic
(ADR-053 §E: contract/specification only; the adapter wiring is a later sprint).

PCI-DSS — NO FULL PAN / CVV / PIN IN THE CONTRACT
-------------------------------------------------
R-SEC-PCI-01 / SPEC #15 Phase D: the cardholder PAN is never stored and is
tokenised via the issuing processor (Paymentology). To keep the cardholder data
environment (CDE) and PCI-DSS scope minimal, this CONTRACT carries ONLY:
  - masked_pan  : a display-safe masked string (e.g. "**** **** **** 1234");
  - last_four   : the last four digits (display only);
  - opaque references (card_id, processor_token).
The contract MUST NOT define, accept, or return a full PAN, a CVV/CVC/CVV2, a
PIN, or any track data. Any adapter that fulfils this port MUST keep those values
inside the processor / CDE and out of every CardView, request, and result here.

CONFORMANCE TEST SUITE
-----------------------
Conformance tests (IDs 1-7) per CONTRACT SPEC enforce the behavioural contract
documented on each method and exception class below.

  1. read_card(known)        -> CardView (masked_pan only); unknown -> CardNotFound
  2. read_limits(known)      -> CardLimits; unknown -> CardNotFound
  3. freeze(active)          -> CardView status=FROZEN; idempotent on FROZEN
  4. unfreeze(frozen)        -> CardView status=ACTIVE; block(any) -> BLOCKED
  5. block is terminal       -> freeze/unfreeze on BLOCKED -> InvalidCardState
  6. issue_card(request)     -> CardView; idempotent per client_card_id
  7. change_limit(card_id)   -> CardLimits; every mutating op emits one
                                guardian_audit_events row with correlation_id

FUTURE WORK (out of scope here)
--------------------------------
- The CardPort adapter wiring the existing card_issuing domain agent + the
  PaymentologyAdapter behind this port (ADR-053 D3 step 4; SPEC #15 Phase B-C).
- The mask-governed CardsAgent in services/agents/ (ADR-053 D3 step 3).
- The Cards mask catalogue entry values (cost_cap, step-up thresholds) as
  config-as-data (ADR-053 D4; CLAUDE.md §10).
- Paymentology appointment (S20) gating go-live (R-EXT-02).
"""

from __future__ import annotations

import abc
from abc import abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

CardId = str
# Opaque, processor-issued token standing in for the tokenised PAN. NEVER a PAN.
ProcessorToken = str

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class CardStatus(StrEnum):
    """Lifecycle status of a card (mirrors the domain CardStatus).

    Transitions relevant to the mask allow-list:
      PENDING --activate--> ACTIVE
      ACTIVE  --freeze--> FROZEN --unfreeze--> ACTIVE
      any     --block--> BLOCKED   (terminal; irreversible — ADR-053 protective)
    """

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"
    REPLACED = "REPLACED"


class CardNetwork(StrEnum):
    """Card scheme network."""

    MASTERCARD = "MASTERCARD"
    VISA = "VISA"


class CardType(StrEnum):
    """Form factor of an issued card."""

    VIRTUAL = "VIRTUAL"
    PHYSICAL = "PHYSICAL"


class SpendPeriod(StrEnum):
    """Window over which a spend limit applies."""

    DAILY = "DAILY"
    MONTHLY = "MONTHLY"
    PER_TRANSACTION = "PER_TRANSACTION"


# ---------------------------------------------------------------------------
# Value objects  (frozen=True — immutable after construction)
#
# PCI-DSS: NONE of these carry a full PAN, CVV/CVC, PIN, or track data. Only a
# display-safe masked_pan, last_four, and opaque references are permitted.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CardView:
    """Display-safe snapshot of a card returned by read/mutation operations.

    PCI-DSS (R-SEC-PCI-01): this is the ONLY card representation crossing the
    contract boundary and it is display-safe by construction — `masked_pan` and
    `last_four` are the sole pan-derived fields, and the full PAN/CVV/PIN are
    absent by design. `processor_token` is the opaque tokenised-PAN reference
    held by the issuing processor; it is NOT a PAN.

    Required fields:
      card_id     — opaque canonical card identifier.
      status      — current lifecycle status.
      masked_pan  — display-safe masked PAN (e.g. "**** **** **** 1234").
      network     — card scheme network.
      card_type   — VIRTUAL or PHYSICAL.
      last_four   — last four PAN digits (display only).
      expiry_month/expiry_year — printed expiry (not sensitive auth data).
      name_on_card — cardholder display name.

    Optional fields:
      processor_token — opaque processor reference to the tokenised PAN; None
                        until the processor has issued one.
    """

    card_id: CardId
    status: CardStatus
    masked_pan: str
    network: CardNetwork
    card_type: CardType
    last_four: str
    expiry_month: int
    expiry_year: int
    name_on_card: str
    processor_token: ProcessorToken | None = None


@dataclass(frozen=True)
class CardLimits:
    """Spend limits for a card, as returned by read_limits / change_limit.

    I-01 / money rule (CLAUDE.md): monetary amounts are Decimal, never float.

    Required fields:
      card_id      — owning card identifier.
      period       — window the limit applies over.
      limit_amount — the cap (Decimal).
      currency     — ISO-4217 currency of limit_amount.

    Optional fields (default to empty lists):
      blocked_mccs     — merchant category codes blocked for this card.
      geo_restrictions — ISO country codes the card is restricted to/from.
    """

    card_id: CardId
    period: SpendPeriod
    limit_amount: Decimal
    currency: str
    blocked_mccs: list[str] = field(default_factory=list)
    geo_restrictions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IssueCardRequest:
    """Request to issue a new card (ADR-053 D4: REVIEW + biometric step-up).

    PCI-DSS: issuance carries NO PAN/CVV/PIN — the processor generates and
    tokenises card credentials; the contract only names the product to issue.

    Required fields:
      entity_id      — customer/entity the card is issued to.
      card_type      — VIRTUAL or PHYSICAL.
      network        — desired card scheme network.
      currency       — ISO-4217 settlement currency of the card.
      name_on_card   — cardholder name to print.
      actor          — identity initiating issuance (for audit / lineage).
      correlation_id — links the issuance to its originating business flow;
                       stored in guardian_audit_events (ADR-027).

    Optional fields:
      client_card_id — caller-supplied idempotency key; a repeated issue_card
                       with the same client_card_id MUST be a no-op returning the
                       original CardView (SPEC #15: idempotent on clientCardId).
    """

    entity_id: str
    card_type: CardType
    network: CardNetwork
    currency: str
    name_on_card: str
    actor: str
    correlation_id: str
    client_card_id: str | None = None


@dataclass(frozen=True)
class LimitChange:
    """Requested change to a card's spend limits (ADR-053 D4: REVIEW + step-up).

    I-01 / money rule: limit_amount is Decimal, never float.

    Required fields:
      period         — window the new limit applies over.
      limit_amount   — the new cap (Decimal).
      currency       — ISO-4217 currency of limit_amount.
      actor          — identity initiating the change (for audit / lineage).
      correlation_id — links the change to its originating business flow.

    Optional fields (default to empty lists):
      blocked_mccs     — merchant category codes to block.
      geo_restrictions — ISO country codes to restrict to/from.
    """

    period: SpendPeriod
    limit_amount: Decimal
    currency: str
    actor: str
    correlation_id: str
    blocked_mccs: list[str] = field(default_factory=list)
    geo_restrictions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Error hierarchy
# (all carry correlation_id; adapters persist exactly one guardian_audit_events
#  row per failed mutating operation before re-raising — ADR-027)
# ---------------------------------------------------------------------------


class CardPortError(Exception):
    """Base for all CardPort errors.

    Every subclass carries correlation_id so the adapter can write exactly one
    guardian_audit_events row per failed operation before re-raising (ADR-027).
    Keyword-only argument forces callers to supply the identifier explicitly
    (mirrors KYCProviderError / CRMProviderError).
    """

    def __init__(self, message: str, *, correlation_id: str) -> None:
        super().__init__(message)
        self.correlation_id: str = correlation_id


class CardNotFound(CardPortError):
    """card_id does not resolve to any card.

    Caller action: surface to user; do not retry with the same id
    (conformance tests 1-2).
    """


class InvalidCardState(CardPortError):
    """The requested transition is illegal for the card's current status.

    Examples: freeze/unfreeze on a BLOCKED card (block is terminal — test 5),
    or changing limits on an EXPIRED/REPLACED card.
    Caller action: do not retry; the state machine forbids this transition.
    """


class ComplianceBlock(CardPortError):
    """An AML/PII compliance gate (ADR-016) blocked the operation.

    Raised when issue_card / change_limit fails the compliance contour, or a
    read fails the PII overlay. Caller action: do not retry; escalate to the
    compliance/MLRO path. Adapter MUST log the blocked attempt to
    guardian_audit_events.
    """


class CardLimitValidationError(CardPortError):
    """A limit change failed structural/business validation before application.

    Triggers: non-positive limit_amount, unknown currency, malformed MCC.
    Caller action: fix and resubmit; do not retry as-is.
    """


class DuplicateIssuance(CardPortError):
    """issue_card was called with a client_card_id already used for a DIFFERENT
    request.

    The idempotent happy path returns the original CardView (no error). This is
    raised ONLY when the same client_card_id is reused with conflicting request
    fields, which the caller must treat as a hard error (SPEC #15 idempotency).
    """


# ---------------------------------------------------------------------------
# Abstract port
# ---------------------------------------------------------------------------


class CardPort(abc.ABC):
    """Abstract CONTRACT for governed card operations (ADR-053 C22 Cards mask).

    This port is the ADR-053 D2 boundary object: the Cards mask `scope`
    allow-lists exactly the operations below; the mask-governed CardsAgent calls
    them through the ADR-049 §D2 chain; the existing card_issuing domain agent is
    the adapter behind them. Nothing outside this surface is client-reachable.

    Conformance rules (enforced by the conformance suite, CONTRACT SPEC):

    PCI-DSS (R-SEC-PCI-01):
      No method accepts or returns a full PAN, CVV/CVC, PIN, or track data. The
      only card representation crossing the boundary is CardView (masked_pan +
      last_four + opaque references). PAN tokenisation lives in the adapter.

    Idempotency:
      freeze       — idempotent per card_id (re-freezing a FROZEN card is a
                     no-op success).
      block        — terminal; once BLOCKED a card stays BLOCKED.
      issue_card   — idempotent per IssueCardRequest.client_card_id.
      change_limit — applying identical limits is a no-op success.

    Read-only operations:
      read_card and read_limits MUST NOT trigger any state change and MUST NOT
      emit a mutating audit row (they still pass the ADR-016 PII overlay).

    Audit (ADR-027) / Lineage (ADR-046):
      Every mutating operation (freeze, block, unfreeze, issue_card,
      change_limit) MUST emit exactly one guardian_audit_events row containing
      correlation_id / actor / card_id / operation / status / timestamp_utc, and
      (at the mask layer) one AgentDecisionRecord per action on every exit path.
    """

    @abstractmethod
    async def freeze(
        self,
        card_id: CardId,
        actor: str,
        reason: str,
    ) -> CardView:
        """Freeze a card (protective; ADR-053 D4 AUTO-with-cap).

        Idempotency contract:
          Freezing an already-FROZEN card is a no-op success returning the
          current CardView; no second audit row is written (conformance test 3).

        Audit (ADR-027): emits exactly one guardian_audit_events row per
        state-changing call with correlation_id, actor, card_id, reason.

        Args:
            card_id: card to freeze.
            actor:   identity initiating the freeze (audit / lineage).
            reason:  human-readable reason (non-PII) for the freeze.

        Returns:
            CardView with status == CardStatus.FROZEN.

        Raises:
            CardNotFound:     card_id unknown.
            InvalidCardState: card is BLOCKED (terminal) or otherwise unfreezable.
        """
        ...

    @abstractmethod
    async def block(
        self,
        card_id: CardId,
        actor: str,
        reason: str,
    ) -> CardView:
        """Block a card permanently (protective, TERMINAL; ADR-053 D4).

        block is irreversible: a BLOCKED card cannot be unfrozen or re-activated
        (conformance test 5).

        Audit (ADR-027): emits exactly one guardian_audit_events row with
        correlation_id, actor, card_id, reason.

        Args:
            card_id: card to block.
            actor:   identity initiating the block (audit / lineage).
            reason:  human-readable reason (non-PII) for the block.

        Returns:
            CardView with status == CardStatus.BLOCKED.

        Raises:
            CardNotFound: card_id unknown.
        """
        ...

    @abstractmethod
    async def unfreeze(
        self,
        card_id: CardId,
        actor: str,
    ) -> CardView:
        """Lift a freeze, returning the card to ACTIVE (ADR-053 D4).

        Idempotency contract:
          Unfreezing an already-ACTIVE card is a no-op success.

        Audit (ADR-027): emits exactly one guardian_audit_events row per
        state-changing call with correlation_id, actor, card_id.

        Args:
            card_id: card to unfreeze.
            actor:   identity initiating the unfreeze (audit / lineage).

        Returns:
            CardView with status == CardStatus.ACTIVE.

        Raises:
            CardNotFound:     card_id unknown.
            InvalidCardState: card is BLOCKED (terminal — cannot be unfrozen).
        """
        ...

    @abstractmethod
    async def read_card(self, card_id: CardId) -> CardView:
        """Return a display-safe snapshot of a card.

        Read-only; MUST NOT trigger any state change or emit a mutating audit
        row (conformance test 1). Passes the ADR-016 PII overlay.

        PCI-DSS: returns CardView (masked_pan only) — never a full PAN/CVV/PIN.

        Args:
            card_id: card to read.

        Returns:
            CardView for the card.

        Raises:
            CardNotFound: card_id unknown (conformance test 1).
        """
        ...

    @abstractmethod
    async def read_limits(self, card_id: CardId) -> CardLimits:
        """Return the current spend limits for a card.

        Read-only; MUST NOT trigger any state change or emit a mutating audit
        row (conformance test 2).

        Args:
            card_id: card whose limits to read.

        Returns:
            CardLimits for the card.

        Raises:
            CardNotFound: card_id unknown (conformance test 2).
        """
        ...

    @abstractmethod
    async def issue_card(self, request: IssueCardRequest) -> CardView:
        """Issue a new card (value/credit-affecting; ADR-053 D4 REVIEW + step-up).

        Idempotency contract:
          A repeated call with the same request.client_card_id MUST be a no-op
          returning the original CardView (conformance test 6). Reusing a
          client_card_id with conflicting fields raises DuplicateIssuance.

        PCI-DSS: the processor generates and tokenises the PAN; the returned
        CardView carries only masked_pan / last_four / processor_token.

        Audit (ADR-027) / compliance (ADR-016): passes the AML contour; emits
        exactly one guardian_audit_events row with request.correlation_id.

        Args:
            request: immutable issuance request including correlation_id and the
                     optional client_card_id idempotency key.

        Returns:
            CardView for the newly issued (or idempotently returned) card.

        Raises:
            ComplianceBlock:    AML/compliance gate blocked issuance.
            DuplicateIssuance:  client_card_id reused with conflicting fields.
        """
        ...

    @abstractmethod
    async def change_limit(
        self,
        card_id: CardId,
        new_limits: LimitChange,
    ) -> CardLimits:
        """Change a card's spend limits (value/credit; ADR-053 D4 REVIEW + step-up).

        Idempotency contract:
          Applying limits identical to the current ones is a no-op success
          returning the current CardLimits (no second audit row).

        Audit (ADR-027) / compliance (ADR-016): a limit increase passes the AML
        contour; emits exactly one guardian_audit_events row with
        new_limits.correlation_id (conformance test 7).

        Args:
            card_id:    card whose limits to change.
            new_limits: the requested limit change including correlation_id.

        Returns:
            CardLimits reflecting the applied limits.

        Raises:
            CardNotFound:             card_id unknown.
            InvalidCardState:         card not in a limit-changeable state.
            CardLimitValidationError: limit_amount/currency/MCC invalid.
            ComplianceBlock:          AML/compliance gate blocked the change.
        """
        ...
