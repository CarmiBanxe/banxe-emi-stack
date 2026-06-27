"""
test_regdata_return.py — Tests for FCA RegData Monthly Return Service (S6-12)
FCA CASS 15 / PS25/12 | banxe-emi-stack
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.reporting.regdata_return import (
    LiveRegDataClient,
    MockFIN060Generator,
    RegDataNotConfiguredError,
    RegDataReturn,
    RegDataReturnService,
    ReturnStatus,
    StubRegDataClient,
    _previous_month_period,
)


class TestPreviousMonthPeriod:
    def test_returns_tuple_of_dates(self):
        start, end = _previous_month_period()
        assert isinstance(start, date)
        assert isinstance(end, date)

    def test_start_is_first_of_month(self):
        start, _ = _previous_month_period()
        assert start.day == 1

    def test_end_is_last_of_month(self):
        import calendar

        start, end = _previous_month_period()
        expected_last = calendar.monthrange(start.year, start.month)[1]
        assert end.day == expected_last

    def test_period_is_previous_month(self):
        today = date.today()
        prev_month = today.month - 1 if today.month > 1 else 12
        start, _ = _previous_month_period()
        assert start.month == prev_month


class TestRegDataReturn:
    def test_deadline_is_15th_of_next_month(self):
        return_ = RegDataReturn(
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            frn="000001",
            avg_daily_client_funds=Decimal("100000"),
            peak_client_funds=Decimal("150000"),
            currency="GBP",
            safeguarding_method="segregated",
        )
        assert return_.deadline == date(2026, 4, 15)

    def test_deadline_december_wraps_to_january(self):
        return_ = RegDataReturn(
            period_start=date(2026, 12, 1),
            period_end=date(2026, 12, 31),
            frn="000001",
            avg_daily_client_funds=Decimal("0"),
            peak_client_funds=Decimal("0"),
            currency="GBP",
            safeguarding_method="segregated",
        )
        assert return_.deadline == date(2027, 1, 15)

    def test_is_overdue_past_deadline(self):
        return_ = RegDataReturn(
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            frn="000001",
            avg_daily_client_funds=Decimal("0"),
            peak_client_funds=Decimal("0"),
            currency="GBP",
            safeguarding_method="segregated",
            status=ReturnStatus.PENDING,
        )
        assert return_.is_overdue is True  # deadline was 2025-02-15

    def test_not_overdue_if_accepted(self):
        return_ = RegDataReturn(
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 31),
            frn="000001",
            avg_daily_client_funds=Decimal("0"),
            peak_client_funds=Decimal("0"),
            currency="GBP",
            safeguarding_method="segregated",
            status=ReturnStatus.ACCEPTED,
        )
        assert return_.is_overdue is False


class TestMockFIN060Generator:
    def test_returns_path_and_amounts(self):
        gen = MockFIN060Generator(avg=Decimal("100000"), peak=Decimal("150000"))
        path, avg, peak = gen.generate(date(2026, 3, 1), date(2026, 3, 31))
        assert isinstance(path, Path)
        assert avg == Decimal("100000")
        assert peak == Decimal("150000")


class TestStubRegDataClient:
    def test_returns_stub_id(self):
        client = StubRegDataClient()
        return_ = RegDataReturn(
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            frn="123456",
            avg_daily_client_funds=Decimal("0"),
            peak_client_funds=Decimal("0"),
            currency="GBP",
            safeguarding_method="segregated",
        )
        sid = client.submit(return_, Path("/tmp/test.pdf"))
        assert "STUB" in sid
        assert "123456" in sid


class TestRegDataReturnService:
    @pytest.fixture
    def service(self):
        return RegDataReturnService(
            generator=MockFIN060Generator(),
            client=StubRegDataClient(),
            frn="999999",
        )

    def test_run_returns_submitted_status(self, service):
        result = service.run_monthly_return(
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )
        assert result.status == ReturnStatus.SUBMITTED

    def test_submission_id_set(self, service):
        result = service.run_monthly_return(
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )
        assert result.submission_id is not None

    def test_submitted_at_set(self, service):
        result = service.run_monthly_return(
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )
        assert result.submitted_at is not None
        assert result.submitted_at.tzinfo is not None

    def test_avg_and_peak_populated(self, service):
        result = service.run_monthly_return(
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )
        assert result.avg_daily_client_funds == Decimal("100000")
        assert result.peak_client_funds == Decimal("150000")

    def test_frn_is_set(self, service):
        result = service.run_monthly_return(
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )
        assert result.frn == "999999"

    def test_no_errors(self, service):
        result = service.run_monthly_return(
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )
        assert result.errors == []

    def test_pdf_path_set(self, service):
        result = service.run_monthly_return(
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )
        assert result.pdf_path is not None
        assert "FIN060" in result.pdf_path

    def test_generator_failure_returns_failed_status(self, service):
        bad_gen = MagicMock()
        bad_gen.generate.side_effect = RuntimeError("ClickHouse down")
        svc = RegDataReturnService(generator=bad_gen, client=StubRegDataClient())
        result = svc.run_monthly_return(
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
        )
        assert result.status == ReturnStatus.SUBMISSION_FAILED
        assert len(result.errors) == 1

    def test_default_period_is_previous_month(self, service):
        result = service.run_monthly_return()
        today = date.today()
        prev_month = today.month - 1 if today.month > 1 else 12
        assert result.period_start.month == prev_month


# ── LiveRegDataClient ─────────────────────────────────────────────────────────


def _make_return(frn: str = "123456") -> RegDataReturn:
    return RegDataReturn(
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        frn=frn,
        avg_daily_client_funds=Decimal("100000"),
        peak_client_funds=Decimal("150000"),
        currency="GBP",
        safeguarding_method="segregated",
    )


class TestLiveRegDataClient:
    def test_raises_runtime_error_without_api_key(self, monkeypatch, tmp_path):
        monkeypatch.delenv("FCA_REGDATA_API_KEY", raising=False)
        import services.reporting.regdata_return as m

        monkeypatch.setattr(m, "REGDATA_API_KEY", "")
        client = LiveRegDataClient()
        pdf = tmp_path / "fin060.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub")
        with pytest.raises(RuntimeError, match="FCA_REGDATA_API_KEY"):
            client.submit(_make_return(), pdf)

    def test_submit_always_raises_runtime_error(self, tmp_path):
        # BT-006v2: LiveRegDataClient.submit is a RuntimeError stub until FCA_REGDATA_API_KEY
        # is provisioned and live HTTP POST is implemented (P1).
        client = LiveRegDataClient()
        pdf = tmp_path / "FIN060_202603.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub")
        with pytest.raises(RuntimeError, match="FCA_REGDATA_API_KEY"):
            client.submit(_make_return(), pdf)

    def test_submit_raises_regardless_of_pdf_content(self, tmp_path):
        client = LiveRegDataClient()
        pdf = tmp_path / "other.pdf"
        pdf.write_bytes(b"")
        with pytest.raises(RegDataNotConfiguredError):
            client.submit(_make_return(frn="654321"), pdf)

    def test_submit_error_message_contains_frn_guidance(self, tmp_path):
        client = LiveRegDataClient()
        pdf = tmp_path / "FIN060_202603.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub")
        with pytest.raises(RegDataNotConfiguredError) as exc_info:
            client.submit(_make_return(), pdf)
        assert "FCA_FRN" in str(exc_info.value)

    def test_submit_raises_for_any_frn(self, tmp_path):
        client = LiveRegDataClient()
        pdf = tmp_path / "FIN060_202501.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub")
        with pytest.raises(RegDataNotConfiguredError, match="FCA_REGDATA_API_KEY"):
            client.submit(_make_return(frn="999999"), pdf)

    def test_submit_raises_not_returns_none(self, tmp_path):
        client = LiveRegDataClient()
        pdf = tmp_path / "FIN060_202603.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub")
        raised = False
        try:
            client.submit(_make_return(), pdf)
        except RegDataNotConfiguredError:
            raised = True
        assert raised, "LiveRegDataClient.submit must raise, never silently succeed"

    def test_live_regdata_client_raises_regdatanotconfigurederror_when_key_absent(
        self, monkeypatch, tmp_path
    ):
        """LiveRegDataClient must raise RegDataNotConfiguredError fail-closed when key absent."""
        import services.reporting.regdata_return as rdr

        monkeypatch.setattr(rdr, "REGDATA_API_KEY", "")
        monkeypatch.setattr(rdr, "FRN", "000000")

        client = LiveRegDataClient()
        return_ = RegDataReturn(
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
            frn="000000",
            avg_daily_client_funds=Decimal("100000"),
            peak_client_funds=Decimal("150000"),
            currency="GBP",
            safeguarding_method="segregated",
        )
        pdf = tmp_path / "FIN060_202605.pdf"
        pdf.write_bytes(b"%PDF-1.4 stub")

        with pytest.raises(RegDataNotConfiguredError, match="BT-010"):
            client.submit(return_, pdf)

    def test_regdata_return_service_draft_mode_works_without_key(self, monkeypatch):
        """Draft mode (PDF generation) works even when RegData key is absent — Variant B."""
        import services.reporting.regdata_return as rdr

        monkeypatch.setattr(rdr, "REGDATA_API_KEY", "")
        monkeypatch.setattr(rdr, "FRN", "000000")

        # Use MockFIN060Generator (default) + LiveRegDataClient
        service = RegDataReturnService(client=LiveRegDataClient())
        result = service.run_monthly_return(date(2026, 5, 1), date(2026, 5, 31))

        # Draft: PDF generated, submission failed (not crashed) — correct Variant B
        assert result.pdf_path is not None
        assert result.status == ReturnStatus.SUBMISSION_FAILED
        assert any("BT-010" in e or "blocked" in e.lower() for e in result.errors)
