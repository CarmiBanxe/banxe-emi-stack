"""services/shared/mask_policy.py — typed loader for mask config-as-data.

WHY THIS FILE EXISTS
--------------------
AnalyticsPort / AnalyticsClientAgent and StatementPort / StatementClientAgent
(ADR-054, ADR-055) already model cost caps, confidence bands, and escalation
roles as governed config, not hardcoded flow logic — but no config-as-data file
existed for either mask before this patchset (CLAUDE.md Configuration-over-
Hardcoding). This module is the typed loading/model surface for
`config/masks/analytics-mask-policy.yaml` and
`config/masks/statements-mask-policy.yaml`, following the same schema-versioned,
Decimal-as-quoted-string, fail-closed convention already established by
`config/runtime_gate/agent-budget-policy.yaml`.

SCOPE OF THIS MODULE (deliberately narrow)
-------------------------------------------
This module ONLY parses and validates the two YAML files into typed, immutable
value objects. It does NOT:
  - implement AnalyticsPort or StatementPort (no adapter here),
  - wire any MCP tool,
  - change the behaviour of any existing MCP tool or API route.
It is a config-as-data substrate for a later, separately-approved patchset.

FAIL-LOUD CONTRACT
------------------
- Missing file, unparsable YAML, or a schema/mask_id mismatch -> raised
  immediately (MaskPolicyFileNotFound / MaskPolicySchemaError).
- `status: PROPOSED` with required fields left `null` is NOT an error — that is
  the honest current state (no operator/counsel values supplied yet).
- `status: ACTIVE` with ANY required field still `null` IS an error
  (MaskPolicyNotReady) — a half-configured file can never silently pass as
  ready for a future adapter to consume.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Error hierarchy (typed, no bare Exception raised by this module)
# ---------------------------------------------------------------------------


class MaskPolicyError(Exception):
    """Base error for all mask-policy config loading/validation failures.

    Args:
        message: Human-readable description of the failure.
        code: Machine-readable error code (snake_case), for callers that need
            to branch without string-matching the message.
    """

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class MaskPolicyFileNotFound(MaskPolicyError):
    """The mask-policy YAML file does not exist at the expected path."""

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"Mask policy file not found: {path}", code="mask_policy_file_not_found"
        )
        self.path = path


class MaskPolicySchemaError(MaskPolicyError):
    """The file exists but is not valid YAML, or its schema/mask_id is wrong."""


class MaskPolicyNotReady(MaskPolicyError):
    """status: ACTIVE was set while one or more required fields are still null.

    Caller action: do not treat this policy as usable. Fix the config file
    (either revert status to PROPOSED, or supply the missing operator/counsel
    value) before any adapter or MCP tool is allowed to depend on it.
    """


# ---------------------------------------------------------------------------
# Shared value objects
# ---------------------------------------------------------------------------


class MaskPolicyStatus(StrEnum):
    """Lifecycle status of a mask policy file.

    PROPOSED: loaded successfully, but one or more fields may still be
    operator/counsel-pending (null). ACTIVE: every required field must be set,
    enforced by the loader (MaskPolicyNotReady otherwise).
    """

    PROPOSED = "PROPOSED"
    ACTIVE = "ACTIVE"


class DeliveryAction(StrEnum):
    """Whether a mask operation completes AUTO or steps to human REVIEW."""

    AUTO = "AUTO"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class CostCap:
    """Token and monetary cost cap, per-request AND per-window (ADR-047 §D2 — both
    dimensions are required; the client agents' own docstrings are explicit that caps
    apply at both grains, not just per-window).

    Required fields:
      window            — rolling window, e.g. "24h".
      currency          — ISO-4217 currency of the monetary caps.

    Optional fields (None = not yet operator/counsel-supplied):
      max_tokens_window  — token budget per window.
      max_cost_window    — monetary cap per window (Decimal, never float — I-01).
      max_request_tokens — token budget per single request.
      max_request_cost   — monetary cap per single request (Decimal, never float).
    """

    window: str
    currency: str
    max_tokens_window: int | None = None
    max_cost_window: Decimal | None = None
    max_request_tokens: int | None = None
    max_request_cost: Decimal | None = None

    @property
    def is_configured(self) -> bool:
        """True once all four numeric caps have been supplied."""
        return (
            self.max_tokens_window is not None
            and self.max_cost_window is not None
            and self.max_request_tokens is not None
            and self.max_request_cost is not None
        )


@dataclass(frozen=True)
class ConfidenceBands:
    """AUTO / REVIEW confidence thresholds for a mask (ADR-049 §D4 shape).

    Optional fields (None = not yet operator/counsel-confirmed against ADR-047):
      auto_min_confidence   — confidence at/above which an action is AUTO-eligible.
      review_min_confidence — confidence at/above which an action steps to REVIEW
                              (rather than BLOCK) when below the AUTO band.
    """

    auto_min_confidence: float | None = None
    review_min_confidence: float | None = None

    @property
    def is_configured(self) -> bool:
        """True once both bands have been supplied."""
        return self.auto_min_confidence is not None and self.review_min_confidence is not None


@dataclass(frozen=True)
class EscalationRoles:
    """Who a blocked/REVIEW-gated action escalates to (ADR-016 / ADR-054/055).

    Optional fields (None = not yet operator/counsel-confirmed):
      pii_compliance_block — role/identity a ComplianceBlock escalates to.
      data_egress_review   — role/identity a data-egress REVIEW escalates to.
    """

    pii_compliance_block: str | None = None
    data_egress_review: str | None = None

    @property
    def is_configured(self) -> bool:
        """True once both escalation roles have been supplied."""
        return self.pii_compliance_block is not None and self.data_egress_review is not None


# ---------------------------------------------------------------------------
# Analytics (C7) mask policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExportMateriality:
    """Materiality threshold gating AnalyticsPort.request_export (ADR-054 §D1).

    Optional fields (None = not yet operator/counsel-supplied):
      max_auto_export_bytes — below this size, an export completes AUTO.
      max_auto_export_rows  — optional alternate dimension (row count).
    """

    max_auto_export_bytes: int | None = None
    max_auto_export_rows: int | None = None

    @property
    def is_configured(self) -> bool:
        """True once at least one materiality dimension has been supplied."""
        return self.max_auto_export_bytes is not None or self.max_auto_export_rows is not None


@dataclass(frozen=True)
class AnalyticsMaskPolicy:
    """Typed, validated content of config/masks/analytics-mask-policy.yaml.

    Required fields:
      mask_id           — must equal "analytics_c7".
      status            — PROPOSED or ACTIVE (see MaskPolicyStatus).
      cost_cap          — token/monetary cost cap (ADR-047).
      confidence_bands  — AUTO/REVIEW confidence thresholds.
      export_materiality — materiality threshold for request_export.
      escalation_roles  — PII/data-egress escalation roles.
    """

    mask_id: str
    status: MaskPolicyStatus
    cost_cap: CostCap
    confidence_bands: ConfidenceBands
    export_materiality: ExportMateriality
    escalation_roles: EscalationRoles


# ---------------------------------------------------------------------------
# Statements mask policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeliveryChannelClassification:
    """AUTO/REVIEW classification per delivery channel (ADR-055 §D1).

    Unlike the other fields in this module, these values are fixed by
    StatementPort's own documented contract (IN_APP=AUTO, EMAIL/EXPORT=REVIEW)
    — they are not operator-pending, and `is_configured` is always True.

    Required fields:
      in_app — DeliveryAction for the IN_APP channel.
      email  — DeliveryAction for the EMAIL channel.
      export — DeliveryAction for the EXPORT channel.
    """

    in_app: DeliveryAction
    email: DeliveryAction
    export: DeliveryAction

    @property
    def is_configured(self) -> bool:
        """Always True — this classification is fixed by the port contract."""
        return True


@dataclass(frozen=True)
class StatementsMaskPolicy:
    """Typed, validated content of config/masks/statements-mask-policy.yaml.

    Required fields:
      mask_id            — must equal "statements".
      status             — PROPOSED or ACTIVE (see MaskPolicyStatus).
      cost_cap           — token/monetary cost cap (ADR-047).
      confidence_bands   — AUTO/REVIEW confidence thresholds.
      delivery_channel_classification — AUTO/REVIEW per delivery channel.
      escalation_roles   — PII/data-egress escalation roles.
    """

    mask_id: str
    status: MaskPolicyStatus
    cost_cap: CostCap
    confidence_bands: ConfidenceBands
    delivery_channel_classification: DeliveryChannelClassification
    escalation_roles: EscalationRoles


# ---------------------------------------------------------------------------
# Shared parsing helpers
# ---------------------------------------------------------------------------

_DEFAULT_ANALYTICS_PATH = Path("config/masks/analytics-mask-policy.yaml")
_DEFAULT_STATEMENTS_PATH = Path("config/masks/statements-mask-policy.yaml")


def _read_yaml(path: Path) -> dict[str, Any]:
    """Read and parse a mask-policy YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        The parsed top-level mapping.

    Raises:
        MaskPolicyFileNotFound: `path` does not exist.
        MaskPolicySchemaError: the file is not valid YAML, or its top level
            is not a mapping.
    """
    if not path.is_file():
        raise MaskPolicyFileNotFound(path)
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise MaskPolicySchemaError(
            f"Failed to parse {path} as YAML: {exc}", code="mask_policy_invalid_yaml"
        ) from exc
    if not isinstance(loaded, dict):
        raise MaskPolicySchemaError(
            f"{path} did not parse to a mapping (got {type(loaded).__name__})",
            code="mask_policy_invalid_shape",
        )
    return loaded


def _parse_decimal(value: Any, *, field: str) -> Decimal | None:
    """Parse an optional Decimal field from its quoted-string YAML form (I-01).

    Args:
        value: The raw YAML value (expected: None or a string).
        field: Field name, for error messages.

    Returns:
        None if `value` is None, otherwise the parsed Decimal.

    Raises:
        MaskPolicySchemaError: `value` is present but not a valid Decimal string.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise MaskPolicySchemaError(
            f"Field '{field}' is not a valid Decimal string: {value!r}",
            code="mask_policy_invalid_decimal",
        ) from exc


def _parse_cost_cap(raw: dict[str, Any]) -> CostCap:
    """Parse the shared `cost_cap` block."""
    return CostCap(
        window=raw["window"],
        currency=raw["currency"],
        max_tokens_window=raw.get("max_tokens_window"),
        max_cost_window=_parse_decimal(raw.get("max_cost_window"), field="max_cost_window"),
        max_request_tokens=raw.get("max_request_tokens"),
        max_request_cost=_parse_decimal(
            raw.get("max_request_cost"), field="max_request_cost"
        ),
    )


def _parse_confidence_bands(raw: dict[str, Any]) -> ConfidenceBands:
    """Parse the shared `confidence_bands` block."""
    return ConfidenceBands(
        auto_min_confidence=raw.get("auto_min_confidence"),
        review_min_confidence=raw.get("review_min_confidence"),
    )


def _parse_escalation_roles(raw: dict[str, Any]) -> EscalationRoles:
    """Parse the shared `escalation_roles` block."""
    return EscalationRoles(
        pii_compliance_block=raw.get("pii_compliance_block"),
        data_egress_review=raw.get("data_egress_review"),
    )


def _require_ready_if_active(*, status: MaskPolicyStatus, blocks: dict[str, Any]) -> None:
    """Enforce the fail-loud contract: ACTIVE requires every block configured.

    Args:
        status: The policy's declared status.
        blocks: Mapping of block name -> object exposing `.is_configured`.

    Raises:
        MaskPolicyNotReady: `status` is ACTIVE but at least one block is not
            fully configured.
    """
    if status is not MaskPolicyStatus.ACTIVE:
        return
    unconfigured = [name for name, block in blocks.items() if not block.is_configured]
    if unconfigured:
        raise MaskPolicyNotReady(
            "status: ACTIVE but required field(s) still unset in: "
            + ", ".join(sorted(unconfigured)),
            code="mask_policy_not_ready",
        )


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------


def load_analytics_mask_policy(path: Path | None = None) -> AnalyticsMaskPolicy:
    """Load and validate config/masks/analytics-mask-policy.yaml.

    Args:
        path: Override path (defaults to the canonical repo-relative path).

    Returns:
        A validated AnalyticsMaskPolicy. May have status PROPOSED with `null`
        (None) fields still pending operator/counsel input — that is a valid,
        honest result, not an error.

    Raises:
        MaskPolicyFileNotFound: the file does not exist.
        MaskPolicySchemaError: the file is invalid YAML, has the wrong
            `schema`/`mask_id`, or a field has the wrong type.
        MaskPolicyNotReady: `status: ACTIVE` is set but a required field is
            still unset.
    """
    resolved = path or _DEFAULT_ANALYTICS_PATH
    raw = _read_yaml(resolved)
    if raw.get("schema") != "analytics-mask-policy/v1":
        raise MaskPolicySchemaError(
            f"Unexpected schema in {resolved}: {raw.get('schema')!r}",
            code="mask_policy_schema_mismatch",
        )
    if raw.get("mask_id") != "analytics_c7":
        raise MaskPolicySchemaError(
            f"Unexpected mask_id in {resolved}: {raw.get('mask_id')!r}",
            code="mask_policy_mask_id_mismatch",
        )

    status = MaskPolicyStatus(raw["status"])
    cost_cap = _parse_cost_cap(raw["cost_cap"])
    confidence_bands = _parse_confidence_bands(raw["confidence_bands"])
    export_raw = raw["export_materiality"]
    export_materiality = ExportMateriality(
        max_auto_export_bytes=export_raw.get("max_auto_export_bytes"),
        max_auto_export_rows=export_raw.get("max_auto_export_rows"),
    )
    escalation_roles = _parse_escalation_roles(raw["escalation_roles"])

    _require_ready_if_active(
        status=status,
        blocks={
            "cost_cap": cost_cap,
            "confidence_bands": confidence_bands,
            "export_materiality": export_materiality,
            "escalation_roles": escalation_roles,
        },
    )

    return AnalyticsMaskPolicy(
        mask_id=raw["mask_id"],
        status=status,
        cost_cap=cost_cap,
        confidence_bands=confidence_bands,
        export_materiality=export_materiality,
        escalation_roles=escalation_roles,
    )


def load_statements_mask_policy(path: Path | None = None) -> StatementsMaskPolicy:
    """Load and validate config/masks/statements-mask-policy.yaml.

    Args:
        path: Override path (defaults to the canonical repo-relative path).

    Returns:
        A validated StatementsMaskPolicy. May have status PROPOSED with `null`
        (None) fields still pending operator/counsel input — that is a valid,
        honest result, not an error.

    Raises:
        MaskPolicyFileNotFound: the file does not exist.
        MaskPolicySchemaError: the file is invalid YAML, has the wrong
            `schema`/`mask_id`, or a field has the wrong type.
        MaskPolicyNotReady: `status: ACTIVE` is set but a required field is
            still unset.
    """
    resolved = path or _DEFAULT_STATEMENTS_PATH
    raw = _read_yaml(resolved)
    if raw.get("schema") != "statements-mask-policy/v1":
        raise MaskPolicySchemaError(
            f"Unexpected schema in {resolved}: {raw.get('schema')!r}",
            code="mask_policy_schema_mismatch",
        )
    if raw.get("mask_id") != "statements":
        raise MaskPolicySchemaError(
            f"Unexpected mask_id in {resolved}: {raw.get('mask_id')!r}",
            code="mask_policy_mask_id_mismatch",
        )

    status = MaskPolicyStatus(raw["status"])
    cost_cap = _parse_cost_cap(raw["cost_cap"])
    confidence_bands = _parse_confidence_bands(raw["confidence_bands"])
    channel_raw = raw["delivery_channel_classification"]
    delivery_channel_classification = DeliveryChannelClassification(
        in_app=DeliveryAction(channel_raw["IN_APP"]),
        email=DeliveryAction(channel_raw["EMAIL"]),
        export=DeliveryAction(channel_raw["EXPORT"]),
    )
    escalation_roles = _parse_escalation_roles(raw["escalation_roles"])

    _require_ready_if_active(
        status=status,
        blocks={
            "cost_cap": cost_cap,
            "confidence_bands": confidence_bands,
            "delivery_channel_classification": delivery_channel_classification,
            "escalation_roles": escalation_roles,
        },
    )

    return StatementsMaskPolicy(
        mask_id=raw["mask_id"],
        status=status,
        cost_cap=cost_cap,
        confidence_bands=confidence_bands,
        delivery_channel_classification=delivery_channel_classification,
        escalation_roles=escalation_roles,
    )
