"""
test_fin060.py — FIN060 Generator smoke tests
IL-015 Step 5 | FCA CASS 15 / PS25/12 | banxe-emi-stack

Covers:
  - FIN060Data dataclass construction
  - _build_html() produces valid HTML with correct figures
  - generate_fin060() smoke test (mock WeasyPrint + mock ClickHouse)
  - _fetch_period_data() raises RuntimeError when clickhouse-driver not installed
  - PDF filename follows convention FIN060_YYYYMM.pdf
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestFIN060DataClass:

    def test_fin060data_construction(self):
        from services.reporting.fin060_generator import FIN060Data
        d = FIN060Data(
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            avg_daily_client_funds=Decimal("125000.00"),
            peak_client_funds=Decimal("200000.00"),
            safeguarding_method="segregated",
            bank_name="Barclays Bank PLC",
            account_number_masked="****7890",
        )
        assert d.currency == "GBP"
        assert d.period_start == date(2026, 3, 1)
        assert d.avg_daily_client_funds == Decimal("125000.00")

    def test_fin060data_immutable(self):
        from services.reporting.fin060_generator import FIN060Data
        import pytest
        d = FIN060Data(
            period_start=date(2026, 3, 1), period_end=date(2026, 3, 31),
            avg_daily_client_funds=Decimal("0"), peak_client_funds=Decimal("0"),
            safeguarding_method="segregated", bank_name="Test Bank",
            account_number_masked="****0000",
        )
        with pytest.raises((AttributeError, TypeError)):
            d.currency = "EUR"  # type: ignore[misc]


class TestBuildHtml:

    def _make_data(self) -> "FIN060Data":  # noqa: F821
        from services.reporting.fin060_generator import FIN060Data
        return FIN060Data(
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            avg_daily_client_funds=Decimal("125000.00"),
            peak_client_funds=Decimal("210000.00"),
            safeguarding_method="segregated",
            bank_name="Barclays Bank PLC",
            account_number_masked="****7890",
        )

    def test_html_contains_period(self):
        from services.reporting.fin060_generator import _build_html
        html = _build_html(self._make_data())
        assert "March 2026" in html

    def test_html_contains_avg_balance(self):
        from services.reporting.fin060_generator import _build_html
        html = _build_html(self._make_data())
        assert "125,000.00" in html

    def test_html_contains_peak_balance(self):
        from services.reporting.fin060_generator import _build_html
        html = _build_html(self._make_data())
        assert "210,000.00" in html

    def test_html_contains_bank_name(self):
        from services.reporting.fin060_generator import _build_html
        html = _build_html(self._make_data())
        assert "Barclays Bank PLC" in html

    def test_html_contains_fca_reference(self):
        from services.reporting.fin060_generator import _build_html
        html = _build_html(self._make_data())
        assert "FIN060" in html
        assert "FCA CASS 15" in html

    def test_html_contains_segregated_method(self):
        from services.reporting.fin060_generator import _build_html
        html = _build_html(self._make_data())
        assert "Segregated" in html


class TestGenerateFIN060:

    def test_generate_returns_pdf_path(self, tmp_path):
        """generate_fin060() returns Path to PDF (WeasyPrint + dir mocked)."""
        import services.reporting.fin060_generator as gen_module

        mock_html_instance = MagicMock()
        mock_html_instance.write_pdf = MagicMock()

        mock_rows = [[Decimal("125000.00"), Decimal("210000.00")]]
        mock_ch_client = MagicMock()
        mock_ch_client.execute.return_value = mock_rows

        mock_ch_driver = MagicMock()
        mock_ch_driver.Client.return_value = mock_ch_client

        mock_weasyprint = MagicMock()
        mock_weasyprint.HTML.return_value = mock_html_instance

        with patch.dict("sys.modules", {
            "weasyprint": mock_weasyprint,
            "clickhouse_driver": mock_ch_driver,
        }), patch.object(gen_module, "FIN060_OUTPUT_DIR", tmp_path):
            pdf_path = gen_module.generate_fin060(date(2026, 3, 1), date(2026, 3, 31))

        assert isinstance(pdf_path, Path)
        assert "FIN060_202603" in pdf_path.name
        assert pdf_path.suffix == ".pdf"

    def test_generate_calls_weasyprint(self, tmp_path):
        """generate_fin060() calls HTML().write_pdf() once."""
        import services.reporting.fin060_generator as gen_module

        mock_html_instance = MagicMock()
        mock_html_instance.write_pdf = MagicMock()

        mock_rows = [[Decimal("50000.00"), Decimal("80000.00")]]
        mock_ch_client = MagicMock()
        mock_ch_client.execute.return_value = mock_rows

        mock_ch_driver = MagicMock()
        mock_ch_driver.Client.return_value = mock_ch_client

        mock_weasyprint = MagicMock()
        mock_weasyprint.HTML.return_value = mock_html_instance

        with patch.dict("sys.modules", {
            "weasyprint": mock_weasyprint,
            "clickhouse_driver": mock_ch_driver,
        }), patch.object(gen_module, "FIN060_OUTPUT_DIR", tmp_path):
            gen_module.generate_fin060(date(2026, 3, 1), date(2026, 3, 31))

        assert mock_html_instance.write_pdf.called

    def test_fetch_period_raises_when_clickhouse_driver_missing(self, tmp_path, monkeypatch):
        """RuntimeError raised when clickhouse-driver not installed."""
        import pytest
        with patch.dict("sys.modules", {"clickhouse_driver": None}):
            import importlib
            import services.reporting.fin060_generator as gen_module
            importlib.reload(gen_module)
            with pytest.raises(RuntimeError, match="clickhouse-driver"):
                gen_module._fetch_period_data(date(2026, 3, 1), date(2026, 3, 31))

    def test_zero_balance_when_no_rows(self, tmp_path, monkeypatch):
        """_fetch_period_data returns Decimal('0') when ClickHouse returns empty."""
        monkeypatch.setenv("FIN060_OUTPUT_DIR", str(tmp_path))

        mock_ch_client = MagicMock()
        mock_ch_client.execute.return_value = []

        mock_ch_driver = MagicMock()
        mock_ch_driver.Client.return_value = mock_ch_client

        import importlib
        import services.reporting.fin060_generator as gen_module

        with patch.dict("sys.modules", {"clickhouse_driver": mock_ch_driver}):
            importlib.reload(gen_module)
            data = gen_module._fetch_period_data(date(2026, 3, 1), date(2026, 3, 31))

        assert data.avg_daily_client_funds == Decimal("0")
        assert data.peak_client_funds == Decimal("0")
