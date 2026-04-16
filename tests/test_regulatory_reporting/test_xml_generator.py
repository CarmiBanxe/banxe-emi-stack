"""
tests/test_regulatory_reporting/test_xml_generator.py
IL-RRA-01 | Phase 14

Tests for FCARegDataXMLGenerator — 6 report types, I-01 Decimal compliance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.regulatory_reporting.models import ReportPeriod, ReportRequest, ReportType
from services.regulatory_reporting.xml_generator import FCARegDataXMLGenerator, _fmt_amount

# ── Fixtures ──────────────────────────────────────────────────────────────────


def make_request(report_type: ReportType) -> ReportRequest:
    return ReportRequest(
        report_type=report_type,
        period=ReportPeriod(
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2025, 1, 31, tzinfo=UTC),
        ),
        entity_id="FRN123456",
        entity_name="Banxe EMI Ltd",
        submitter_id="test-actor",
        template_version="v3",
    )


@pytest.fixture()
def generator() -> FCARegDataXMLGenerator:
    return FCARegDataXMLGenerator()


# ── _fmt_amount ───────────────────────────────────────────────────────────────


def test_fmt_amount_rounds_to_2dp() -> None:
    assert _fmt_amount(Decimal("1234567.891")) == "1234567.89"


def test_fmt_amount_zero() -> None:
    assert _fmt_amount(Decimal("0")) == "0.00"


def test_fmt_amount_exact_pence() -> None:
    assert _fmt_amount(Decimal("99.99")) == "99.99"


# ── FIN060 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_fin060_contains_required_tags(generator: FCARegDataXMLGenerator) -> None:
    request = make_request(ReportType.FIN060)
    data = {
        "total_client_assets": "500000.00",
        "segregated_amount": "498000.00",
        "shortfall": "0.00",
    }
    xml = await generator.generate(request, data)
    assert "<?xml" in xml
    assert "<FIN060Return" in xml
    assert "<FirmRef>FRN123456</FirmRef>" in xml
    assert "<TotalClientAssets" in xml
    assert "500000.00" in xml


@pytest.mark.asyncio
async def test_generate_fin060_period_in_header(generator: FCARegDataXMLGenerator) -> None:
    request = make_request(ReportType.FIN060)
    xml = await generator.generate(request, {})
    assert "2025-01-01" in xml
    assert "2025-01-31" in xml


@pytest.mark.asyncio
async def test_generate_fin060_zero_amounts_default(generator: FCARegDataXMLGenerator) -> None:
    xml = await generator.generate(make_request(ReportType.FIN060), {})
    assert "0.00" in xml


# ── FIN071 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_fin071_structure(generator: FCARegDataXMLGenerator) -> None:
    xml = await generator.generate(
        make_request(ReportType.FIN071),
        {"total_client_assets": "9999999.99", "client_count": 100},
    )
    assert "<FIN071Return" in xml
    assert "<TotalAssets" in xml
    assert "9999999.99" in xml
    assert "<ClientCount>100</ClientCount>" in xml


@pytest.mark.asyncio
async def test_generate_fin071_entity_name(generator: FCARegDataXMLGenerator) -> None:
    xml = await generator.generate(make_request(ReportType.FIN071), {})
    assert "<FirmName>Banxe EMI Ltd</FirmName>" in xml


# ── FSA076 ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_fsa076_annual_income(generator: FCARegDataXMLGenerator) -> None:
    xml = await generator.generate(
        make_request(ReportType.FSA076),
        {"annual_income": "250000.00", "fee_block": "CC3"},
    )
    assert "<FSA076Return" in xml
    assert "<AnnualIncome" in xml
    assert "250000.00" in xml
    assert "<FeeBlock>CC3</FeeBlock>" in xml


# ── SAR_BATCH ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_sar_batch_multiple_reports(generator: FCARegDataXMLGenerator) -> None:
    sars = [
        {
            "ref": "SAR-001",
            "subject_type": "INDIVIDUAL",
            "amount": "5000.00",
            "activity_type": "ML",
        },
        {
            "ref": "SAR-002",
            "subject_type": "CORPORATE",
            "amount": "75000.00",
            "activity_type": "TF",
        },
    ]
    xml = await generator.generate(
        make_request(ReportType.SAR_BATCH),
        {"sar_reports": sars},
    )
    assert "<SARBatch" in xml
    assert "<BatchSize>2</BatchSize>" in xml
    assert "SAR-001" in xml
    assert "SAR-002" in xml
    assert "5000.00" in xml
    assert "75000.00" in xml


@pytest.mark.asyncio
async def test_generate_sar_batch_empty(generator: FCARegDataXMLGenerator) -> None:
    xml = await generator.generate(make_request(ReportType.SAR_BATCH), {"sar_reports": []})
    assert "<BatchSize>0</BatchSize>" in xml


# ── BOE_FORM_BT ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_boe_form_bt(generator: FCARegDataXMLGenerator) -> None:
    xml = await generator.generate(
        make_request(ReportType.BOE_FORM_BT),
        {"total_lending": "1000000.00", "total_deposits": "5000000.00"},
    )
    assert "<BoEFormBT" in xml
    assert "<TotalLending" in xml
    assert "1000000.00" in xml
    assert "5000000.00" in xml


# ── ACPR_EMI ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_acpr_emi(generator: FCARegDataXMLGenerator) -> None:
    xml = await generator.generate(
        make_request(ReportType.ACPR_EMI),
        {"e_money_issued": "300000.00", "holder_count": 500},
    )
    assert "<ACPRReturn" in xml
    assert "<EMoneyIssued" in xml
    assert "300000.00" in xml
    assert "<HolderCount>500</HolderCount>" in xml
    assert "<Jurisdiction>FR</Jurisdiction>" in xml


# ── Unsupported type ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_unsupported_type_raises(generator: FCARegDataXMLGenerator) -> None:
    from services.regulatory_reporting.models import ReportPeriod, ReportRequest

    request = ReportRequest(
        report_type=ReportType.FIN060,
        period=ReportPeriod(
            start=datetime(2025, 1, 1, tzinfo=UTC), end=datetime(2025, 1, 31, tzinfo=UTC)
        ),
        entity_id="X",
        entity_name="X",
        submitter_id="X",
    )
    # Monkey-patch to simulate unknown type
    from services.regulatory_reporting import xml_generator as xg

    original = xg._BUILDERS.pop(ReportType.FIN060)
    try:
        with pytest.raises(ValueError, match="Unsupported report type"):
            await generator.generate(request, {})
    finally:
        xg._BUILDERS[ReportType.FIN060] = original
