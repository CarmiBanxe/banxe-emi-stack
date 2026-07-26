"""tests/test_shared_mask_policy.py — tests for services/shared/mask_policy.py.

Covers: loading the real shipped config/masks/*.yaml files (PROPOSED, as shipped),
the fail-loud contract (missing file, bad schema, ACTIVE-with-unset-field), and
Decimal / channel-classification parsing correctness.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from services.shared.mask_policy import (
    DeliveryAction,
    MaskPolicyFileNotFound,
    MaskPolicyNotReady,
    MaskPolicySchemaError,
    MaskPolicyStatus,
    load_analytics_mask_policy,
    load_statements_mask_policy,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
ANALYTICS_PATH = REPO_ROOT / "config" / "masks" / "analytics-mask-policy.yaml"
STATEMENTS_PATH = REPO_ROOT / "config" / "masks" / "statements-mask-policy.yaml"


def test_load_analytics_mask_policy_as_shipped_is_proposed_with_nulls() -> None:
    policy = load_analytics_mask_policy(ANALYTICS_PATH)
    assert policy.mask_id == "analytics_c7"
    assert policy.status == MaskPolicyStatus.PROPOSED
    assert policy.cost_cap.max_tokens_window is None
    assert policy.cost_cap.max_cost_window is None
    assert policy.cost_cap.currency == "GBP"
    assert not policy.cost_cap.is_configured
    assert not policy.confidence_bands.is_configured
    assert not policy.export_materiality.is_configured
    assert not policy.escalation_roles.is_configured


def test_load_statements_mask_policy_as_shipped_is_proposed_with_nulls() -> None:
    policy = load_statements_mask_policy(STATEMENTS_PATH)
    assert policy.mask_id == "statements"
    assert policy.status == MaskPolicyStatus.PROPOSED
    assert not policy.cost_cap.is_configured
    assert not policy.confidence_bands.is_configured
    assert not policy.escalation_roles.is_configured


def test_statements_delivery_channel_classification_is_fixed_and_configured() -> None:
    policy = load_statements_mask_policy(STATEMENTS_PATH)
    dcc = policy.delivery_channel_classification
    assert dcc.in_app == DeliveryAction.AUTO
    assert dcc.email == DeliveryAction.REVIEW
    assert dcc.export == DeliveryAction.REVIEW
    assert dcc.is_configured  # always True — fixed by the port contract


def test_missing_file_raises_mask_policy_file_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.yaml"
    with pytest.raises(MaskPolicyFileNotFound) as exc_info:
        load_analytics_mask_policy(missing)
    assert exc_info.value.code == "mask_policy_file_not_found"


def test_invalid_yaml_raises_mask_policy_schema_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("mask_id: [unterminated", encoding="utf-8")
    with pytest.raises(MaskPolicySchemaError) as exc_info:
        load_analytics_mask_policy(bad)
    assert exc_info.value.code == "mask_policy_invalid_yaml"


def test_wrong_mask_id_raises_mask_policy_schema_error(tmp_path: Path) -> None:
    wrong = tmp_path / "wrong.yaml"
    wrong.write_text(
        """
schema: analytics-mask-policy/v1
mask_id: not_analytics_c7
status: PROPOSED
cost_cap: {window: 24h, currency: GBP}
confidence_bands: {}
export_materiality: {}
escalation_roles: {}
""",
        encoding="utf-8",
    )
    with pytest.raises(MaskPolicySchemaError) as exc_info:
        load_analytics_mask_policy(wrong)
    assert exc_info.value.code == "mask_policy_mask_id_mismatch"


def test_active_status_with_unset_field_raises_mask_policy_not_ready(tmp_path: Path) -> None:
    half_configured = tmp_path / "half.yaml"
    half_configured.write_text(
        """
schema: analytics-mask-policy/v1
mask_id: analytics_c7
status: ACTIVE
cost_cap: {window: 24h, currency: GBP, max_tokens_window: 200000, max_cost_window: "5.00", max_request_tokens: 20000, max_request_cost: "0.50"}
confidence_bands: {auto_min_confidence: 0.9, review_min_confidence: 0.7}
export_materiality: {max_auto_export_bytes: 1000000}
escalation_roles: {pii_compliance_block: null, data_egress_review: dpo}
""",
        encoding="utf-8",
    )
    with pytest.raises(MaskPolicyNotReady) as exc_info:
        load_analytics_mask_policy(half_configured)
    assert exc_info.value.code == "mask_policy_not_ready"
    assert "escalation_roles" in str(exc_info.value)


def test_active_status_fully_configured_loads_successfully(tmp_path: Path) -> None:
    fully_configured = tmp_path / "full.yaml"
    fully_configured.write_text(
        """
schema: analytics-mask-policy/v1
mask_id: analytics_c7
status: ACTIVE
cost_cap: {window: 24h, currency: GBP, max_tokens_window: 200000, max_cost_window: "5.00", max_request_tokens: 20000, max_request_cost: "0.50"}
confidence_bands: {auto_min_confidence: 0.9, review_min_confidence: 0.7}
export_materiality: {max_auto_export_bytes: 1000000}
escalation_roles: {pii_compliance_block: dpo, data_egress_review: dpo}
""",
        encoding="utf-8",
    )
    policy = load_analytics_mask_policy(fully_configured)
    assert policy.status == MaskPolicyStatus.ACTIVE
    assert policy.cost_cap.max_cost_window == Decimal("5.00")
    assert policy.cost_cap.is_configured
    assert policy.confidence_bands.is_configured
    assert policy.export_materiality.is_configured
    assert policy.escalation_roles.is_configured


def test_invalid_decimal_raises_mask_policy_schema_error(tmp_path: Path) -> None:
    bad_decimal = tmp_path / "bad_decimal.yaml"
    bad_decimal.write_text(
        """
schema: analytics-mask-policy/v1
mask_id: analytics_c7
status: PROPOSED
cost_cap: {window: 24h, currency: GBP, max_cost_window: "not-a-number"}
confidence_bands: {}
export_materiality: {}
escalation_roles: {}
""",
        encoding="utf-8",
    )
    with pytest.raises(MaskPolicySchemaError) as exc_info:
        load_analytics_mask_policy(bad_decimal)
    assert exc_info.value.code == "mask_policy_invalid_decimal"
