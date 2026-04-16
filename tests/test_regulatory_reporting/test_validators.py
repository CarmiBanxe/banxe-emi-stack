"""
tests/test_regulatory_reporting/test_validators.py
IL-RRA-01 | Phase 14

Tests for StructuralValidator and XSDValidator.
"""

from __future__ import annotations

import pytest

from services.regulatory_reporting.models import ReportType
from services.regulatory_reporting.validators import StructuralValidator, XSDValidator

# ── Fixtures ──────────────────────────────────────────────────────────────────

VALID_FIN060 = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<FIN060Return xmlns="http://www.fca.org.uk/regdata/fin060/v3">'
    "<FirmRef>FRN123456</FirmRef>"
    "<TotalClientAssets currency='GBP'>500000.00</TotalClientAssets>"
    "</FIN060Return>"
)

VALID_FIN071 = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<FIN071Return xmlns="http://www.fca.org.uk/regdata/fin071/v2">'
    "<FirmRef>FRN123456</FirmRef>"
    "<TotalAssets currency='GBP'>9000000.00</TotalAssets>"
    "</FIN071Return>"
)


@pytest.fixture()
def sv() -> StructuralValidator:
    return StructuralValidator()


@pytest.fixture()
def xv() -> XSDValidator:
    return XSDValidator()


# ── StructuralValidator ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_structural_valid_fin060(sv: StructuralValidator) -> None:
    result = await sv.validate(VALID_FIN060, ReportType.FIN060)
    assert result.is_valid is True
    assert result.errors == []


@pytest.mark.asyncio
async def test_structural_missing_xml_declaration(sv: StructuralValidator) -> None:
    xml = (
        "<FIN060Return><FirmRef>X</FirmRef><TotalClientAssets>0</TotalClientAssets></FIN060Return>"
    )
    result = await sv.validate(xml, ReportType.FIN060)
    assert result.is_valid is False
    assert any("XML declaration" in e for e in result.errors)


@pytest.mark.asyncio
async def test_structural_empty_content(sv: StructuralValidator) -> None:
    result = await sv.validate("", ReportType.FIN060)
    assert result.is_valid is False
    assert any("empty" in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_structural_missing_required_tag(sv: StructuralValidator) -> None:
    xml = '<?xml version="1.0"?><FIN060Return><FirmRef>X</FirmRef></FIN060Return>'
    result = await sv.validate(xml, ReportType.FIN060)
    assert result.is_valid is False
    assert any("TotalClientAssets" in e for e in result.errors)


@pytest.mark.asyncio
async def test_structural_forbidden_nan(sv: StructuralValidator) -> None:
    xml = '<?xml version="1.0"?><FIN060Return><FirmRef>X</FirmRef><TotalClientAssets>NaN</TotalClientAssets></FIN060Return>'
    result = await sv.validate(xml, ReportType.FIN060)
    assert result.is_valid is False
    assert any("NaN" in e for e in result.errors)


@pytest.mark.asyncio
async def test_structural_forbidden_infinity(sv: StructuralValidator) -> None:
    xml = VALID_FIN060.replace("500000.00", "Infinity")
    result = await sv.validate(xml, ReportType.FIN060)
    assert result.is_valid is False


@pytest.mark.asyncio
async def test_structural_forbidden_undefined(sv: StructuralValidator) -> None:
    xml = VALID_FIN060.replace("500000.00", "undefined")
    result = await sv.validate(xml, ReportType.FIN060)
    assert result.is_valid is False


@pytest.mark.asyncio
async def test_structural_zero_amount_warning(sv: StructuralValidator) -> None:
    xml = VALID_FIN060.replace("500000.00", "0.00")
    result = await sv.validate(xml, ReportType.FIN060)
    assert result.is_valid is True  # zero is not an error, just a warning
    assert any("zero" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_structural_valid_fin071(sv: StructuralValidator) -> None:
    result = await sv.validate(VALID_FIN071, ReportType.FIN071)
    assert result.is_valid is True


@pytest.mark.asyncio
async def test_structural_schema_version(sv: StructuralValidator) -> None:
    result = await sv.validate(VALID_FIN060, ReportType.FIN060)
    assert result.schema_version == "structural-v1"


@pytest.mark.asyncio
async def test_structural_validated_at_is_set(sv: StructuralValidator) -> None:
    result = await sv.validate(VALID_FIN060, ReportType.FIN060)
    assert result.validated_at is not None


@pytest.mark.asyncio
async def test_structural_no_required_tags_for_unknown_type(sv: StructuralValidator) -> None:
    # SAR_BATCH has its own tags; validate FIN060 xml against SAR returns missing SAR tags
    result = await sv.validate(VALID_FIN060, ReportType.SAR_BATCH)
    assert result.is_valid is False
    assert any("SARBatch" in e for e in result.errors)


# ── XSDValidator ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_xsd_validator_graceful_without_xmlschema(xv: XSDValidator) -> None:
    """XSDValidator must fall back to structural if xmlschema not installed."""
    xv._xmlschema_available = False
    result = await xv.validate(VALID_FIN060, ReportType.FIN060)
    assert any("xmlschema library not installed" in w for w in result.warnings)
    assert result.schema_version == "structural-only"


@pytest.mark.asyncio
async def test_xsd_validator_graceful_schema_not_found(xv: XSDValidator) -> None:
    """XSDValidator falls back gracefully if XSD file is missing."""
    if not xv._xmlschema_available:
        pytest.skip("xmlschema not installed")
    result = await xv.validate(VALID_FIN060, ReportType.FIN060)
    # Schema file not present → structural fallback with warning
    assert any("not found" in w or "structural" in w for w in result.warnings) or result.is_valid


@pytest.mark.asyncio
async def test_xsd_validator_no_template_returns_error(xv: XSDValidator) -> None:
    if not xv._xmlschema_available:
        pytest.skip("xmlschema not installed")

    # Temporarily remove FIN060 from templates
    from services.regulatory_reporting.models import REPORT_TEMPLATES

    original = REPORT_TEMPLATES.pop(ReportType.FIN060)
    try:
        result = await xv.validate(VALID_FIN060, ReportType.FIN060)
        assert result.is_valid is False
        assert any("No XSD schema" in e for e in result.errors)
    finally:
        REPORT_TEMPLATES[ReportType.FIN060] = original
