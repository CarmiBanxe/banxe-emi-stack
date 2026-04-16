"""
services/regulatory_reporting/xml_generator.py — FCA RegData XML Generator
IL-RRA-01 | Phase 14 | banxe-emi-stack

Generates regulatory XML for FIN060 / FIN071 / FSA076 / SAR Batch / BoE / ACPR.
Uses Jinja2 templating with lxml for structure validation.

FCA refs: SUP 16.12 (regulatory reporting), SUP 16.20 (fees data)
I-01: all monetary amounts use Decimal — never float
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import logging

from services.regulatory_reporting.models import (
    REPORT_TEMPLATES,
    ReportAmount,
    ReportRequest,
    ReportType,
)

logger = logging.getLogger(__name__)

# Decimal precision for XML serialisation
_AMOUNT_PRECISION = 2  # pennies: £1,234,567.89


def _fmt_amount(amount: ReportAmount | Decimal) -> str:
    """Format Decimal amount for XML — always 2 decimal places. I-01 compliant."""
    return f"{amount:.{_AMOUNT_PRECISION}f}"


def _fmt_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _fmt_period(start: datetime, end: datetime) -> tuple[str, str]:
    return _fmt_date(start), _fmt_date(end)


# ─── Template builders (pure-Python, no lxml dependency in tests) ─────────────


def _build_fin060_xml(request: ReportRequest, data: dict) -> str:
    """FCA CASS 15 Monthly Safeguarding Return (FIN060 v3)."""
    period_start, period_end = _fmt_period(request.period.start, request.period.end)
    total_assets = _fmt_amount(Decimal(str(data.get("total_client_assets", "0"))))
    segregated = _fmt_amount(Decimal(str(data.get("segregated_amount", "0"))))
    shortfall = _fmt_amount(Decimal(str(data.get("shortfall", "0"))))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<FIN060Return xmlns="http://www.fca.org.uk/regdata/fin060/v3">\n'
        f"  <Header>\n"
        f"    <FirmRef>{request.entity_id}</FirmRef>\n"
        f"    <FirmName>{request.entity_name}</FirmName>\n"
        f"    <ReportingPeriodStart>{period_start}</ReportingPeriodStart>\n"
        f"    <ReportingPeriodEnd>{period_end}</ReportingPeriodEnd>\n"
        f"    <GeneratedAt>{datetime.now(UTC).isoformat()}</GeneratedAt>\n"
        f"    <TemplateVersion>{REPORT_TEMPLATES[ReportType.FIN060].version}</TemplateVersion>\n"
        f"  </Header>\n"
        f"  <SafeguardingData>\n"
        f"    <TotalClientAssets currency='GBP'>{total_assets}</TotalClientAssets>\n"
        f"    <SegregatedAmount currency='GBP'>{segregated}</SegregatedAmount>\n"
        f"    <Shortfall currency='GBP'>{shortfall}</Shortfall>\n"
        f"    <BreachCount>{data.get('breach_count', 0)}</BreachCount>\n"
        f"    <ReconciliationFrequency>{data.get('recon_frequency', 'DAILY')}"
        f"</ReconciliationFrequency>\n"
        f"  </SafeguardingData>\n"
        f"</FIN060Return>"
    )


def _build_fin071_xml(request: ReportRequest, data: dict) -> str:
    """FCA Client Assets Annual Return (FIN071 v2)."""
    period_start, period_end = _fmt_period(request.period.start, request.period.end)
    total_assets = _fmt_amount(Decimal(str(data.get("total_client_assets", "0"))))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<FIN071Return xmlns="http://www.fca.org.uk/regdata/fin071/v2">\n'
        f"  <Header>\n"
        f"    <FirmRef>{request.entity_id}</FirmRef>\n"
        f"    <FirmName>{request.entity_name}</FirmName>\n"
        f"    <ReportingPeriodStart>{period_start}</ReportingPeriodStart>\n"
        f"    <ReportingPeriodEnd>{period_end}</ReportingPeriodEnd>\n"
        f"  </Header>\n"
        f"  <ClientAssets>\n"
        f"    <TotalAssets currency='GBP'>{total_assets}</TotalAssets>\n"
        f"    <ClientCount>{data.get('client_count', 0)}</ClientCount>\n"
        f"    <CustodyArrangement>{data.get('custody_arrangement', 'BANK_ACCOUNT')}"
        f"</CustodyArrangement>\n"
        f"  </ClientAssets>\n"
        f"</FIN071Return>"
    )


def _build_fsa076_xml(request: ReportRequest, data: dict) -> str:
    """FCA Regulated Fees Data (FSA076 v1)."""
    period_start, period_end = _fmt_period(request.period.start, request.period.end)
    income = _fmt_amount(Decimal(str(data.get("annual_income", "0"))))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<FSA076Return xmlns="http://www.fca.org.uk/regdata/fsa076/v1">\n'
        f"  <Header>\n"
        f"    <FirmRef>{request.entity_id}</FirmRef>\n"
        f"    <FirmName>{request.entity_name}</FirmName>\n"
        f"    <PeriodStart>{period_start}</PeriodStart>\n"
        f"    <PeriodEnd>{period_end}</PeriodEnd>\n"
        f"  </Header>\n"
        f"  <FeesData>\n"
        f"    <AnnualIncome currency='GBP'>{income}</AnnualIncome>\n"
        f"    <FeeBlock>{data.get('fee_block', 'CC3')}</FeeBlock>\n"
        f"    <ActivityType>{data.get('activity_type', 'EMI')}</ActivityType>\n"
        f"  </FeesData>\n"
        f"</FSA076Return>"
    )


def _build_sar_batch_xml(request: ReportRequest, data: dict) -> str:
    """NCA SAR Batch Filing (POCA 2002 s.330)."""
    reports = data.get("sar_reports", [])
    sar_items = ""
    for sar in reports:
        amount = _fmt_amount(Decimal(str(sar.get("amount", "0"))))
        sar_items += (
            f"    <SARReport>\n"
            f"      <SARRef>{sar.get('ref', '')}</SARRef>\n"
            f"      <SubjectType>{sar.get('subject_type', 'INDIVIDUAL')}</SubjectType>\n"
            f"      <SuspiciousAmount currency='GBP'>{amount}</SuspiciousAmount>\n"
            f"      <ActivityType>{sar.get('activity_type', 'UNKNOWN')}</ActivityType>\n"
            f"      <ReportedAt>{sar.get('reported_at', datetime.now(UTC).isoformat())}</ReportedAt>\n"
            f"    </SARReport>\n"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<SARBatch xmlns="http://www.nationalcrimeagency.gov.uk/sar/v2">\n'
        f"  <Header>\n"
        f"    <FirmRef>{request.entity_id}</FirmRef>\n"
        f"    <BatchSize>{len(reports)}</BatchSize>\n"
        f"    <SubmissionDate>{_fmt_date(datetime.now(UTC))}</SubmissionDate>\n"
        f"  </Header>\n"
        f"  <Reports>\n"
        f"{sar_items}"
        f"  </Reports>\n"
        f"</SARBatch>"
    )


def _build_boe_form_bt_xml(request: ReportRequest, data: dict) -> str:
    """BoE Form BT Statistical Return."""
    period_start, period_end = _fmt_period(request.period.start, request.period.end)
    total_lending = _fmt_amount(Decimal(str(data.get("total_lending", "0"))))
    total_deposits = _fmt_amount(Decimal(str(data.get("total_deposits", "0"))))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<BoEFormBT xmlns="http://www.bankofengland.co.uk/statistical/form_bt/v1">\n'
        f"  <Header>\n"
        f"    <FirmRef>{request.entity_id}</FirmRef>\n"
        f"    <PeriodStart>{period_start}</PeriodStart>\n"
        f"    <PeriodEnd>{period_end}</PeriodEnd>\n"
        f"  </Header>\n"
        f"  <StatisticalData>\n"
        f"    <TotalLending currency='GBP'>{total_lending}</TotalLending>\n"
        f"    <TotalDeposits currency='GBP'>{total_deposits}</TotalDeposits>\n"
        f"    <FirmType>{data.get('firm_type', 'EMI')}</FirmType>\n"
        f"  </StatisticalData>\n"
        f"</BoEFormBT>"
    )


def _build_acpr_emi_xml(request: ReportRequest, data: dict) -> str:
    """ACPR France EMI Quarterly Return (ACPR 2014-P-01)."""
    period_start, period_end = _fmt_period(request.period.start, request.period.end)
    e_money_issued = _fmt_amount(Decimal(str(data.get("e_money_issued", "0"))))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ACPRReturn xmlns="http://www.acpr.banque-france.fr/emi/v1">\n'
        f"  <Header>\n"
        f"    <FirmRef>{request.entity_id}</FirmRef>\n"
        f"    <FirmName>{request.entity_name}</FirmName>\n"
        f"    <PeriodStart>{period_start}</PeriodStart>\n"
        f"    <PeriodEnd>{period_end}</PeriodEnd>\n"
        f"    <Jurisdiction>FR</Jurisdiction>\n"
        f"  </Header>\n"
        f"  <EMIData>\n"
        f"    <EMoneyIssued currency='EUR'>{e_money_issued}</EMoneyIssued>\n"
        f"    <HolderCount>{data.get('holder_count', 0)}</HolderCount>\n"
        f"    <AverageFloat currency='EUR'>"
        f"{_fmt_amount(Decimal(str(data.get('average_float', '0'))))}"
        f"</AverageFloat>\n"
        f"  </EMIData>\n"
        f"</ACPRReturn>"
    )


# ─── Builder dispatch ─────────────────────────────────────────────────────────

_BUILDERS = {
    ReportType.FIN060: _build_fin060_xml,
    ReportType.FIN071: _build_fin071_xml,
    ReportType.FSA076: _build_fsa076_xml,
    ReportType.SAR_BATCH: _build_sar_batch_xml,
    ReportType.BOE_FORM_BT: _build_boe_form_bt_xml,
    ReportType.ACPR_EMI: _build_acpr_emi_xml,
}


class FCARegDataXMLGenerator:
    """
    Generates regulatory XML for all supported report types.

    Uses pure-Python string templating (no lxml dependency for generation).
    lxml is only used for final structure validation in ValidatorPort.

    Trust Zone: AMBER (generates regulated submissions)
    I-01: all monetary amounts use Decimal — never float
    """

    async def generate(self, request: ReportRequest, financial_data: dict) -> str:
        builder = _BUILDERS.get(request.report_type)
        if builder is None:
            raise ValueError(f"Unsupported report type: {request.report_type}")

        xml = builder(request, financial_data)
        logger.info(
            "Generated XML for %s entity=%s period=%s",
            request.report_type.value,
            request.entity_id,
            request.period.label,
        )
        return xml
