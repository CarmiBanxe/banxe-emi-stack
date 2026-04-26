"""Tests for HMRC FATCA/CRS Annual Reporting (IL-HMR-01)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.fatca_crs.hmrc_models import (
    AccountHolder,
    HMRCReport,
    ReportableAccount,
)
from services.fatca_crs.hmrc_reporter import (
    _DEFAULT_FI,
    BLOCKED_JURISDICTIONS,
    HMRCHITLProposal,
    HMRCReporter,
    InMemoryReportStore,
)


def _make_reporter() -> HMRCReporter:
    return HMRCReporter(InMemoryReportStore())


def _make_account(
    account_id: str = "ACC001",
    customer_id: str = "CUST001",
    country: str = "GB",
    balance: str = "1000.00",
    us_person: bool = False,
    tin: str = "1234567890",
) -> dict:
    return {
        "account_id": account_id,
        "customer_id": customer_id,
        "name": "Test Customer",
        "country": country,
        "balance": balance,
        "tin": tin,
        "us_person": us_person,
        "currency": "GBP",
    }


class TestHMRCReporterGeneration:
    def test_generate_returns_hitl_proposal(self):
        """I-27: generation always requires CFO + MLRO."""
        reporter = _make_reporter()
        result = reporter.generate_annual_report(2025)
        assert isinstance(result, HMRCHITLProposal)

    def test_hitl_not_auto_approved(self):
        """I-27: proposals start unapproved."""
        reporter = _make_reporter()
        result = reporter.generate_annual_report(2025)
        assert isinstance(result, HMRCHITLProposal)
        assert result.approved is False

    def test_hitl_requires_cfo_and_mlro(self):
        reporter = _make_reporter()
        result = reporter.generate_annual_report(2025)
        assert isinstance(result, HMRCHITLProposal)
        assert "CFO" in result.requires_approval_from
        assert "MLRO" in result.requires_approval_from

    def test_proposals_accumulate(self):
        reporter = _make_reporter()
        reporter.generate_annual_report(2024)
        reporter.generate_annual_report(2025)
        assert len(reporter.proposals) == 2

    def test_do_generate_creates_report(self):
        reporter = _make_reporter()
        accounts = [_make_account()]
        report = reporter._do_generate(2025, accounts)
        assert report.report_id is not None
        assert report.tax_year == 2025

    def test_us_person_goes_to_fatca(self):
        reporter = _make_reporter()
        accounts = [_make_account(country="US", us_person=True)]
        report = reporter._do_generate(2025, accounts)
        assert len(report.fatca_accounts) == 1
        assert len(report.crs_accounts) == 0

    def test_non_us_person_goes_to_crs(self):
        reporter = _make_reporter()
        accounts = [_make_account(country="DE", us_person=False)]
        report = reporter._do_generate(2025, accounts)
        assert len(report.crs_accounts) == 1
        assert len(report.fatca_accounts) == 0

    def test_blocked_jurisdiction_ru_excluded(self):
        """I-02: Russian accounts excluded from report."""
        reporter = _make_reporter()
        accounts = [_make_account(country="RU")]
        report = reporter._do_generate(2025, accounts)
        assert report.total_accounts == 0

    def test_blocked_jurisdiction_ir_excluded(self):
        reporter = _make_reporter()
        accounts = [_make_account(country="IR")]
        report = reporter._do_generate(2025, accounts)
        assert report.total_accounts == 0

    def test_balance_is_decimal_string(self):
        reporter = _make_reporter()
        accounts = [_make_account(balance="5000.00")]
        report = reporter._do_generate(2025, accounts)
        for acc in report.crs_accounts + report.fatca_accounts:
            assert isinstance(acc.balance, str)
            Decimal(acc.balance)  # must parse

    def test_balance_not_float(self):
        reporter = _make_reporter()
        accounts = [_make_account(balance="1234.56")]
        report = reporter._do_generate(2025, accounts)
        for acc in report.crs_accounts + report.fatca_accounts:
            assert not isinstance(acc.balance, float)

    def test_report_log_append_only(self):
        """I-24: report_log grows."""
        reporter = _make_reporter()
        reporter._do_generate(2024)
        reporter._do_generate(2025)
        assert len(reporter.report_log) == 2

    def test_blocked_jurisdictions_set(self):
        assert "RU" in BLOCKED_JURISDICTIONS
        assert "GB" not in BLOCKED_JURISDICTIONS

    def test_bt012_submit_raises(self):
        """BT-012: HMRC gateway is a stub."""
        reporter = _make_reporter()
        report = reporter._do_generate(2025)
        with pytest.raises(NotImplementedError, match="BT-012"):
            reporter.submit_to_hmrc_gateway(report)


class TestHMRCValidation:
    def test_valid_report_passes(self):
        reporter = _make_reporter()
        report = reporter._do_generate(2025, [_make_account()])
        result = reporter.validate_report(report)
        assert result.valid is True
        assert result.errors == []

    def test_invalid_year_fails(self):
        reporter = _make_reporter()
        report = HMRCReport(
            report_id="r001",
            tax_year=2010,  # before FATCA/CRS
            fi=_DEFAULT_FI,
            fatca_accounts=[],
            crs_accounts=[],
            generated_at="2026-04-26T00:00:00+00:00",
        )
        result = reporter.validate_report(report)
        assert result.valid is False
        assert any(e.field == "tax_year" for e in result.errors)

    def test_blocked_jurisdiction_in_report_fails(self):
        reporter = _make_reporter()
        holder = AccountHolder(
            account_id="ACC001",
            customer_id="C1",
            name="Bad",
            country_of_residence="RU",
            tin="1234567890",
        )
        acc = ReportableAccount(
            account_id="ACC001",
            account_holder=holder,
            balance="100.00",
            reportable_jurisdiction="RU",
            tax_year=2025,
        )
        report = HMRCReport(
            report_id="r001",
            tax_year=2025,
            fi=_DEFAULT_FI,
            fatca_accounts=[],
            crs_accounts=[acc],
            generated_at="2026-04-26T00:00:00+00:00",
        )
        result = reporter.validate_report(report)
        assert result.valid is False

    def test_validation_result_has_report_id(self):
        reporter = _make_reporter()
        report = reporter._do_generate(2025)
        result = reporter.validate_report(report)
        assert result.report_id == report.report_id

    def test_tin_masked(self):
        holder = AccountHolder(
            account_id="ACC001",
            customer_id="C1",
            name="Test",
            country_of_residence="GB",
            tin="SECRETTIN9",
        )
        assert "SECRETTIN9" not in holder.masked_tin()
        assert holder.masked_tin() == "****TIN9"

    def test_total_accounts_property(self):
        reporter = _make_reporter()
        accounts = [
            _make_account("A1", country="US", us_person=True),
            _make_account("A2", country="DE"),
        ]
        report = reporter._do_generate(2025, accounts)
        assert report.total_accounts == 2
