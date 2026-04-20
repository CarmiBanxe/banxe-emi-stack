"""Tests for services/multi_tenancy/billing_engine.py"""

from decimal import Decimal

import pytest

from services.multi_tenancy.billing_engine import (
    OVERAGE_FEE_PER_TX,
    TIER_MONTHLY_FEE,
    TenantBillingEngine,
)
from services.multi_tenancy.models import (
    HITLProposal,
    InMemoryTenantPort,
    IsolationLevel,
    Tenant,
    TenantStatus,
    TenantTier,
)


def _make_tenant(tenant_id: str, tier: TenantTier) -> Tenant:
    return Tenant(
        tenant_id=tenant_id,
        name="BillingCo",
        tier=tier,
        status=TenantStatus.ACTIVE,
        isolation_level=IsolationLevel.SCHEMA,
        monthly_fee=TIER_MONTHLY_FEE[tier],
        daily_tx_limit=1000,
        jurisdiction="GB",
    )


def _make_engine(
    tenant_id: str = "ten_abc", tier: TenantTier = TenantTier.BASIC
) -> TenantBillingEngine:
    tp = InMemoryTenantPort()
    tp.save(_make_tenant(tenant_id, tier))
    return TenantBillingEngine(tenant_port=tp)


def test_calculate_monthly_invoice_basic():
    eng = _make_engine(tier=TenantTier.BASIC)
    inv = eng.calculate_monthly_invoice("ten_abc", "2026-04")
    assert inv["amount"] == "10.00"
    assert inv["currency"] == "GBP"


def test_calculate_monthly_invoice_business():
    eng = _make_engine(tier=TenantTier.BUSINESS)
    inv = eng.calculate_monthly_invoice("ten_abc", "2026-04")
    assert inv["amount"] == "99.00"


def test_calculate_monthly_invoice_enterprise():
    eng = _make_engine(tier=TenantTier.ENTERPRISE)
    inv = eng.calculate_monthly_invoice("ten_abc", "2026-04")
    assert inv["amount"] == "999.00"


def test_invoice_amount_is_string_not_float():
    eng = _make_engine()
    inv = eng.calculate_monthly_invoice("ten_abc", "2026-04")
    # Amount must be string (I-01 via I-05)
    assert isinstance(inv["amount"], str)


def test_apply_usage_charges_no_overage():
    eng = _make_engine(tier=TenantTier.BASIC)
    overage = eng.apply_usage_charges("ten_abc", tx_count=500, volume_gbp=Decimal("1000.00"))
    assert overage == Decimal("0")


def test_apply_usage_charges_with_overage():
    eng = _make_engine(tier=TenantTier.BASIC)
    # BASIC limit = 1000 tx/day; send 1200 → 200 excess
    overage = eng.apply_usage_charges("ten_abc", tx_count=1200, volume_gbp=Decimal("5000.00"))
    expected = Decimal("200") * OVERAGE_FEE_PER_TX
    assert overage == expected


def test_overage_fee_is_decimal():
    assert isinstance(OVERAGE_FEE_PER_TX, Decimal)


def test_tier_monthly_fees_are_decimal():
    for tier, fee in TIER_MONTHLY_FEE.items():
        assert isinstance(fee, Decimal), f"{tier} fee is not Decimal"


def test_get_billing_summary_fields():
    eng = _make_engine()
    eng.apply_usage_charges("ten_abc", tx_count=100, volume_gbp=Decimal("1000.00"))
    summary = eng.get_billing_summary("ten_abc")
    assert "tenant_id" in summary
    assert "tier" in summary
    assert "monthly_fee" in summary
    assert "total_transactions" in summary
    assert "total_overage" in summary


def test_generate_invoice_has_invoice_id():
    eng = _make_engine()
    inv = eng.generate_invoice("ten_abc", "2026-04")
    assert "invoice_id" in inv
    assert inv["invoice_id"].startswith("inv_")


def test_process_payment_failure_returns_hitl():
    eng = _make_engine()
    proposal = eng.process_payment_failure("ten_abc", "card_declined")
    assert isinstance(proposal, HITLProposal)
    assert proposal.tenant_id == "ten_abc"
    assert proposal.requires_approval_from == "BILLING"


def test_calculate_monthly_invoice_missing_tenant():
    eng = TenantBillingEngine()
    with pytest.raises(ValueError, match="not found"):
        eng.calculate_monthly_invoice("ten_missing", "2026-04")


def test_invoice_includes_period():
    eng = _make_engine()
    inv = eng.calculate_monthly_invoice("ten_abc", "2026-04")
    assert inv["period"] == "2026-04"


def test_total_invoice_includes_overage():
    eng = _make_engine(tier=TenantTier.BASIC)
    eng.apply_usage_charges("ten_abc", tx_count=1100, volume_gbp=Decimal("5000.00"))
    inv = eng.calculate_monthly_invoice("ten_abc", "2026-04")
    expected_overage = Decimal("100") * OVERAGE_FEE_PER_TX
    expected_total = TIER_MONTHLY_FEE[TenantTier.BASIC] + expected_overage
    assert Decimal(inv["amount"]) == expected_total
