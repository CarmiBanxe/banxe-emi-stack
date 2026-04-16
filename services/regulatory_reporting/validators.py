"""
services/regulatory_reporting/validators.py — Report Validation Engine
IL-RRA-01 | Phase 14 | banxe-emi-stack

XSD schema validation for regulatory XML reports.
Uses xmlschema library for XSD 1.0/1.1 compliance checking.

FCA SUP 16: reports must conform to published XSD schemas before submission.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging

from services.regulatory_reporting.models import (
    ReportType,
    ValidationResult,
)

logger = logging.getLogger(__name__)

# Minimum XML content checks (structural, not XSD)
_REQUIRED_TAGS: dict[ReportType, list[str]] = {
    ReportType.FIN060: ["<FIN060Return", "<FirmRef>", "<TotalClientAssets"],
    ReportType.FIN071: ["<FIN071Return", "<FirmRef>", "<TotalAssets"],
    ReportType.FSA076: ["<FSA076Return", "<FirmRef>", "<AnnualIncome"],
    ReportType.SAR_BATCH: ["<SARBatch", "<FirmRef>", "<BatchSize>"],
    ReportType.BOE_FORM_BT: ["<BoEFormBT", "<FirmRef>", "<TotalLending"],
    ReportType.ACPR_EMI: ["<ACPRReturn", "<FirmRef>", "<EMoneyIssued"],
}

_FORBIDDEN_CONTENT = [
    "NaN",
    "Infinity",
    "-Infinity",
    "undefined",
    "null",
]


def _structural_checks(xml_content: str, report_type: ReportType) -> list[str]:
    """Run fast structural checks before XSD validation."""
    errors: list[str] = []

    if not xml_content.strip():
        errors.append("XML content is empty")
        return errors

    if not xml_content.startswith("<?xml"):
        errors.append("Missing XML declaration (<?xml version...?>)")

    required = _REQUIRED_TAGS.get(report_type, [])
    for tag in required:
        if tag not in xml_content:
            errors.append(f"Missing required element: {tag}")

    for forbidden in _FORBIDDEN_CONTENT:
        if forbidden in xml_content:
            errors.append(f"Forbidden value in XML: {forbidden}")

    return errors


class StructuralValidator:
    """
    Fast structural validator using tag-presence checks.

    In production, complement with a full XSD validator (xmlschema lib).
    This validator is suitable for CI/CD gates where xmlschema is not installed.

    Trust Zone: AMBER
    """

    async def validate(self, xml_content: str, report_type: ReportType) -> ValidationResult:
        errors = _structural_checks(xml_content, report_type)
        warnings: list[str] = []

        # Warn if amounts look like they might be zero (common data issue)
        if ">0.00<" in xml_content and report_type in (
            ReportType.FIN060,
            ReportType.FIN071,
            ReportType.BOE_FORM_BT,
        ):
            warnings.append("One or more amounts are zero — verify financial data is complete")

        is_valid = not errors
        if is_valid:
            logger.info("Structural validation PASSED for %s", report_type.value)
        else:
            logger.warning(
                "Structural validation FAILED for %s: %d errors",
                report_type.value,
                len(errors),
            )

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            schema_version="structural-v1",
            validated_at=datetime.now(UTC),
        )


class XSDValidator:
    """
    XSD schema validator using xmlschema library.

    Falls back to structural validation if xmlschema is not installed
    (graceful degradation for environments without the library).
    """

    def __init__(self, schema_dir: str = "services/regulatory_reporting/schemas") -> None:
        self._schema_dir = schema_dir
        self._structural = StructuralValidator()
        self._xmlschema_available = self._check_xmlschema()

    @staticmethod
    def _check_xmlschema() -> bool:
        try:
            import xmlschema  # noqa: F401

            return True
        except ImportError:
            return False

    async def validate(self, xml_content: str, report_type: ReportType) -> ValidationResult:
        if not self._xmlschema_available:
            # Graceful degradation — structural only
            result = await self._structural.validate(xml_content, report_type)
            warnings = list(result.warnings) + [
                "xmlschema library not installed — XSD validation skipped"
            ]
            return ValidationResult(
                is_valid=result.is_valid,
                errors=result.errors,
                warnings=warnings,
                schema_version="structural-only",
                validated_at=result.validated_at,
            )

        # Full XSD validation
        import xmlschema  # noqa: PLC0415

        from services.regulatory_reporting.models import REPORT_TEMPLATES

        template = REPORT_TEMPLATES.get(report_type)
        if template is None:
            return ValidationResult(
                is_valid=False,
                errors=[f"No XSD schema registered for {report_type.value}"],
                warnings=[],
                schema_version="unknown",
                validated_at=datetime.now(UTC),
            )

        schema_path = f"{self._schema_dir}/{template.xsd_schema.split('/')[-1]}"
        try:
            schema = xmlschema.XMLSchema(schema_path)
            is_valid = schema.is_valid(xml_content)
            errors = [str(e) for e in schema.iter_errors(xml_content)]
            return ValidationResult(
                is_valid=is_valid,
                errors=errors,
                warnings=[],
                schema_version=template.version,
                validated_at=datetime.now(UTC),
            )
        except FileNotFoundError:
            # Schema file not found — fall back to structural
            result = await self._structural.validate(xml_content, report_type)
            warnings = list(result.warnings) + [
                f"XSD schema file not found: {schema_path} — structural validation only"
            ]
            return ValidationResult(
                is_valid=result.is_valid,
                errors=result.errors,
                warnings=warnings,
                schema_version="structural-fallback",
                validated_at=result.validated_at,
            )
