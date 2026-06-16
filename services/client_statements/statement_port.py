"""statement_port.py — StatementPort: governed statements CONTRACT (Statements mask).

ADR-055 Statements client-facing mask — the THIRD extended-catalogue entry
(after Cards C22 via ADR-053 and Analytics / Reporting C7 via ADR-054). This file
is the CONTRACT port that the Statements mask `scope` allow-lists.

Referenced ADRs / specs:
  ADR-055  Statements client-facing mask. Defines the mask as a read+generate
           surface — the read-side companion to Analytics (C7), one notch heavier
           on egress: AUTO-with-cap to get/list/generate the client's OWN
           statements, REVIEW to deliver one to an external channel/address
           (data-egress of a PII-bearing funds artefact). NO biometric step-up
           (no money movement); PII overlay + data-egress gate. StatementPort is
           the CONTRACT boundary the mask `scope` allow-lists (ADR-055 §D1/§D3).
  ADR-054  Analytics / Reporting (C7) mask — established the data-egress / export
           gate posture this port reuses for deliver_statement; its §D5 deferred
           Statements to ADR-055.
  ADR-053  Client-facing mask catalogue extensibility; the mask <-> domain-agent
           governance boundary (every mask scopes a real hexagonal CONTRACT port,
           never a client surface directly).
  ADR-049  Intent-layer client-facing agent masks (the §D2 gate chain, §D3 mask
           fields, §D4 thresholds). Statements reuses these unchanged; §D4
           critical money-movement step-up does NOT apply (no value-bearing op).
  ADR-046  Decision Lineage Schema — one AgentDecisionRecord per masked action.
  ADR-047  AI Cost Governance Policy — per-request / per-window cost caps; the
           token caps are emphasised because statement generation can be heavy.
  ADR-016  AI-plane PII/AML routing — PII overlay on any client-fund / personal
           data, plus the data-egress gate on delivery.

WHY THIS FILE EXISTS
--------------------
ADR-055 adds the Statements mask but is SPECIFICATION / CONTRACT ONLY — it authors
no port. A mask may only scope operations on a real hexagonal CONTRACT port
(ADR-053 D1: "no mask may scope a capability that has no port"). StatementPort is
that boundary object: the Statements mask `scope` allow-lists exactly the governed
read/generate/deliver operations defined here, and nothing outside this port is
reachable through the mask.

StatementPort exposes ONLY the ADR-055 §D1 allow-list — the governed
client-surface read/generate/deliver operations:
  reads      : get_statement, list_statements
  generate   : generate_statement   (AUTO-with-cap; heavy generation cost-capped)
  data-egress: deliver_statement     (REVIEW — external egress of a PII artefact)

GOVERNANCE BOUNDARY (ADR-055 D2 — canonical)
--------------------------------------------
StatementPort is the boundary where governance (in front) meets domain
implementation (behind). The mask-governed client-facing StatementAgent sits IN
FRONT of this port and calls it through the full ADR-049 §D2 chain; the existing
domain service-agent `services/client_statements/statement_agent.py` (and its
`statement_generator.py` / `statement_models.py` / internal `StatementDataPort`
collaborators) sits BEHIND this port as the ADAPTER, untouched. A client intent
MUST NOT reach the domain agent directly — especially not its `email_statement`
delivery path — that would be an ungoverned read/PII/egress surface (no lineage,
no cost-cap, no PII overlay, no data-egress gate).

This file authors NO adapter and touches NO existing client_statements logic
(ADR-055 §E: contract / specification only; the adapter wiring is a later sprint).
The pre-existing internal `StatementDataPort` is an implementation detail INSIDE
the adapter, distinct from this governance CONTRACT `StatementPort` that fronts it.

READ / GENERATE / DELIVER ONLY — NO MUTATION, NO MONEY MOVEMENT
--------------------------------------------------------------
ADR-055 §D1: the Statements operations are read / generate / deliver only. NO
method on this port mutates state, moves money, or writes to client balances.
get_statement / list_statements read; generate_statement produces a statement
artefact derived from reads; deliver_statement egresses an already-generated
artefact. None of them is a value-bearing action, so the ADR-049 §D4 biometric
step-up does not apply — deliver_statement steps to REVIEW because it egresses
personal + funds data beyond the application boundary, not because it moves money.

PII — OPAQUE IDENTIFIERS ONLY; RAW TRANSACTION PII STAYS BEHIND THE PORT
-----------------------------------------------------------------------
ADR-016 PII overlay: a statement itemises the client's own transactions and
balances, so it is personal AND funds data. Every identifier crossing this
contract is OPAQUE — `entity_id` / `statement_id` are handles, never raw PII (no
name, email, IBAN, address). StatementView carries the non-sensitive summary
shape (opening/closing balances as Decimal, a line_count) so the client surface
can describe a statement WITHOUT the raw itemised transaction PII crossing the
boundary; that itemised detail stays behind the port inside the adapter.
deliver_statement is the ONLY egress operation and is therefore the REVIEW /
data-egress gate; any adapter fulfilling this port keeps the raw artefact behind
the PII overlay and redacts as the export path requires.

CONFORMANCE TEST SUITE
-----------------------
Conformance tests (IDs 1-5) per CONTRACT SPEC enforce the behavioural contract
documented on each method and exception class below.

  1. get_statement(known)        -> StatementView (Decimal balances); read-only,
                                     no mutation; unknown -> StatementNotFound.
  2. list_statements(eid, period)-> list[StatementDescriptor]; read-only.
  3. generate_statement(request) -> StatementView; AUTO within the cost-cap; a
                                     cap breach / compliance failure -> ComplianceBlock.
  4. deliver_statement(small)    -> DeliveryResult; delivery to an external
                                     channel steps to REVIEW; an egress the gate
                                     forbids -> DeliveryEgressBlocked.
  5. PII / compliance failure on any op -> ComplianceBlock.

FUTURE WORK (out of scope here)
--------------------------------
- The StatementPort adapter wiring the existing client_statements domain agent
  behind this port (ADR-055 D3 step 4; later sprint).
- The mask-governed StatementAgent in services/agents/ (ADR-055 D3 step 3).
- The Statements mask catalogue entry values (cost_cap, the materiality of
  "external delivery") as config-as-data (ADR-055 D1/D4; CLAUDE.md §10).
"""

from __future__ import annotations

import abc
from abc import abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# Opaque customer/entity handle. NEVER raw PII (no name/email/IBAN/address).
EntityId = str
# Opaque canonical statement identifier. NEVER raw PII.
StatementId = str

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class StatementPeriod(StrEnum):
    """Window a statement covers (read / generate parameter)."""

    MONTH = "MONTH"
    QUARTER = "QUARTER"
    YEAR = "YEAR"
    CUSTOM = "CUSTOM"


class StatementFormat(StrEnum):
    """Output format of a generated statement artefact."""

    PDF = "PDF"
    CSV = "CSV"
    JSON = "JSON"


class DeliveryChannel(StrEnum):
    """Channel a generated statement is delivered to (data-egress gate).

    IN_APP keeps the artefact inside the application boundary (AUTO posture);
    EMAIL and EXPORT egress a PII-bearing funds artefact OUTSIDE the application
    and therefore step deliver_statement to REVIEW (ADR-055 data-egress gate).
    """

    IN_APP = "IN_APP"
    EMAIL = "EMAIL"
    EXPORT = "EXPORT"


class DeliveryStatus(StrEnum):
    """Lifecycle status of a deliver_statement request (ADR-055 data-egress gate).

    Transitions relevant to the mask allow-list:
      IN_APP / in-boundary delivery               --> DELIVERED (AUTO)
      external channel                            --> PENDING_REVIEW
      PENDING_REVIEW --(REVIEW approved)--> DELIVERED
      PENDING_REVIEW --(REVIEW rejected / blocked)--> REJECTED
    """

    DELIVERED = "DELIVERED"
    PENDING_REVIEW = "PENDING_REVIEW"
    REJECTED = "REJECTED"


# ---------------------------------------------------------------------------
# Value objects  (frozen=True — immutable after construction)
#
# READ / GENERATE / DELIVER only: none of these carry mutating or money-moving
# intent. PII: identifiers are the opaque EntityId / StatementId only; the raw
# itemised transaction PII stays behind the port, NOT in these summary objects.
# I-01 / money rule (CLAUDE.md): monetary amounts are Decimal, never float.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StatementView:
    """Display-safe summary of a statement returned by get / generate (read-only).

    PII (ADR-016): this is the summary shape the client surface needs to describe
    a statement WITHOUT the raw itemised transaction PII crossing the boundary —
    it carries balances and a line_count, never the per-line transaction detail,
    which stays behind the port inside the adapter.

    I-01 / money rule: `opening_balance` and `closing_balance` are Decimal, never
    float.

    Required fields:
      statement_id    — opaque canonical statement identifier (no raw PII).
      entity_id       — opaque entity the statement belongs to (no raw PII).
      period          — the window the statement covers.
      opening_balance — balance at the start of the period (Decimal).
      closing_balance — balance at the end of the period (Decimal).
      line_count      — number of itemised lines in the statement (a count only;
                        the lines themselves stay behind the port).
      currency        — ISO-4217 currency of the balances.

    Optional fields:
      format — the rendered format, when the statement has been generated to one;
               None for a not-yet-rendered view.
    """

    statement_id: StatementId
    entity_id: EntityId
    period: StatementPeriod
    opening_balance: Decimal
    closing_balance: Decimal
    line_count: int
    currency: str
    format: StatementFormat | None = None


@dataclass(frozen=True)
class StatementDescriptor:
    """A listing entry describing a statement available to an entity (read-only).

    Required fields:
      statement_id — opaque statement identifier (no raw PII).
      period       — the window the statement covers.
      currency     — ISO-4217 currency of the statement.

    Optional fields:
      format — the format the statement is/was rendered to; None if not yet
               generated.
    """

    statement_id: StatementId
    period: StatementPeriod
    currency: str
    format: StatementFormat | None = None


@dataclass(frozen=True)
class GenerateStatementRequest:
    """Request to generate a statement for an entity (ADR-055 AUTO-with-cap).

    Generation can be heavy (multi-period itemisation, document rendering), so the
    ADR-047 per-request / per-window token caps apply; a cap breach halts the
    action (surfaced as ComplianceBlock). No money movement, no fund mutation —
    generation derives a statement artefact from reads.

    Required fields:
      entity_id      — opaque entity to generate the statement for (no raw PII).
      period         — the window to itemise.
      format         — desired output format.
      actor          — identity initiating the generation (for audit / lineage).
      correlation_id — links the generation to its originating business flow.
    """

    entity_id: EntityId
    period: StatementPeriod
    format: StatementFormat
    actor: str
    correlation_id: str


@dataclass(frozen=True)
class DeliveryResult:
    """Result of a deliver_statement call (data-egress; no mutation, no money move).

    deliver_statement is the only egress operation: in-boundary delivery completes
    AUTO (DeliveryStatus.DELIVERED); delivery to an external channel (EMAIL /
    EXPORT) steps to REVIEW (DeliveryStatus.PENDING_REVIEW). The artefact is the
    PII-bearing funds statement, kept behind the PII overlay by the adapter.

    Required fields:
      statement_id — opaque statement that was delivered.
      channel      — the channel delivery was requested to.
      status       — DELIVERED (AUTO / approved) or PENDING_REVIEW (data-egress).

    Optional fields:
      egress_redacted — whether the egressed artefact was PII-redacted; defaults
                        to True (redacted unless the compliance overlay authorises
                        otherwise).
    """

    statement_id: StatementId
    channel: DeliveryChannel
    status: DeliveryStatus
    egress_redacted: bool = True


# ---------------------------------------------------------------------------
# Error hierarchy
# (all carry correlation_id; the adapter persists exactly one audit row per
#  failed operation before re-raising — ADR-027 / ADR-046)
# ---------------------------------------------------------------------------


class StatementPortError(Exception):
    """Base for all StatementPort errors.

    Every subclass carries correlation_id so the adapter can write exactly one
    audit row per failed operation before re-raising. Keyword-only argument forces
    callers to supply the identifier explicitly (mirrors AnalyticsPortError /
    CardPortError).
    """

    def __init__(self, message: str, *, correlation_id: str) -> None:
        super().__init__(message)
        self.correlation_id: str = correlation_id


class StatementNotFound(StatementPortError):
    """statement_id does not resolve to any statement (conformance test 1).

    Caller action: surface to user; do not retry with the same id.
    """


class DeliveryEgressBlocked(StatementPortError):
    """The data-egress gate (ADR-055) blocked delivery to an external channel.

    Raised when deliver_statement to an EMAIL / EXPORT channel is refused by the
    data-egress gate rather than stepping to REVIEW (conformance test 4). Caller
    action: route through the REVIEW / approval path; do not retry the external
    egress as-is.
    """


class ComplianceBlock(StatementPortError):
    """A PII / compliance gate (ADR-016) or cost-cap breach blocked the operation.

    Raised when a read fails the PII overlay, generation breaches the ADR-047
    cost-cap, or delivery requests un-redacted PII the overlay forbids. Caller
    action: do not retry; escalate to the compliance / MLRO path. The adapter MUST
    log the blocked attempt.
    """


# ---------------------------------------------------------------------------
# Abstract port
# ---------------------------------------------------------------------------


class StatementPort(abc.ABC):
    """Abstract CONTRACT for governed statement operations (ADR-055 Statements mask).

    This port is the ADR-055 D2 boundary object: the Statements mask `scope`
    allow-lists exactly the operations below; the mask-governed StatementAgent
    calls them through the ADR-049 §D2 chain; the existing client_statements
    domain agent is the adapter behind them. Nothing outside this surface is
    client-reachable.

    Conformance rules (enforced by the conformance suite, CONTRACT SPEC):

    Read / generate / deliver only (ADR-055 §D1):
      NO operation mutates state, moves money, or writes to client balances.
      get_statement / list_statements read; generate_statement produces an
      artefact derived from reads; deliver_statement egresses an already-generated
      artefact. None is a value-bearing action.

    PII (ADR-016):
      Every identifier is the opaque entity_id / statement_id; no method accepts
      or returns raw PII. StatementView carries balances + a line_count only — the
      raw itemised transaction PII stays behind the port inside the adapter.

    Data-egress gate (ADR-055):
      deliver_statement to an external channel (EMAIL / EXPORT) steps to REVIEW
      (DeliveryStatus.PENDING_REVIEW); an egress the gate forbids raises
      DeliveryEgressBlocked. There is NO biometric step-up — the gate is
      data-egress, not a value-bearing action.

    Cost / lineage (ADR-047 / ADR-046):
      Potentially heavy generation is bounded by the mask cost-cap (token caps
      emphasised); the mask layer emits one AgentDecisionRecord per action on
      every exit path.
    """

    @abstractmethod
    async def get_statement(self, statement_id: StatementId) -> StatementView:
        """Return a display-safe summary of a single statement (read-only).

        Read-only; MUST NOT trigger any state change or move money
        (conformance test 1). Passes the ADR-016 PII overlay; balances are
        Decimal. Returns the summary shape only — the raw itemised transaction
        PII stays behind the port.

        Args:
            statement_id: opaque statement to read (no raw PII).

        Returns:
            StatementView with Decimal opening/closing balances and a line_count.

        Raises:
            StatementNotFound: statement_id unknown (conformance test 1).
            ComplianceBlock:   the PII overlay blocked the read.
        """
        ...

    @abstractmethod
    async def list_statements(
        self,
        entity_id: EntityId,
        period: StatementPeriod,
    ) -> list[StatementDescriptor]:
        """List the statements available to an entity for a period (read-only).

        Read-only; MUST NOT trigger any state change (conformance test 2).

        Args:
            entity_id: opaque entity whose statements to list (no raw PII).
            period:    the window to list statements for.

        Returns:
            A list of StatementDescriptor (possibly empty).

        Raises:
            ComplianceBlock: the PII overlay blocked the read.
        """
        ...

    @abstractmethod
    async def generate_statement(
        self,
        request: GenerateStatementRequest,
    ) -> StatementView:
        """Generate a statement for an entity (ADR-055 AUTO-with-cap).

        Generation derives a statement artefact from reads — it does NOT move
        money or mutate funds. AUTO within the ADR-047 cost-cap; a cap breach
        halts the action (conformance test 3). Passes the ADR-016 PII overlay.

        Args:
            request: immutable generation request including correlation_id and the
                     desired format.

        Returns:
            StatementView for the generated statement (Decimal balances).

        Raises:
            ComplianceBlock: the PII overlay blocked generation, or the ADR-047
                             cost-cap was breached.
        """
        ...

    @abstractmethod
    async def deliver_statement(
        self,
        statement_id: StatementId,
        channel: DeliveryChannel,
    ) -> DeliveryResult:
        """Deliver an already-generated statement (ADR-055 data-egress gate).

        This is the only egress operation. In-boundary delivery (IN_APP) completes
        AUTO (DeliveryStatus.DELIVERED); delivery to an external channel (EMAIL /
        EXPORT) egresses a PII-bearing funds artefact and steps to REVIEW
        (conformance test 4). NO money movement occurs and NO biometric step-up
        applies — the gate is data-egress only. The egressed artefact is
        PII-redacted unless the compliance overlay authorises otherwise.

        Args:
            statement_id: opaque statement to deliver.
            channel:      the channel to deliver to (IN_APP / EMAIL / EXPORT).

        Returns:
            DeliveryResult — DELIVERED (AUTO / approved) or PENDING_REVIEW pending
            the data-egress REVIEW.

        Raises:
            StatementNotFound:     statement_id unknown.
            DeliveryEgressBlocked: the data-egress gate forbade the external egress.
            ComplianceBlock:       the PII / compliance overlay blocked delivery.
        """
        ...
