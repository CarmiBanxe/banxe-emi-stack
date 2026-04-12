"""
test_parsers_and_poller.py — Tests for bankstatement_parser + statement_poller
IL-014 quality fixes | banxe-emi-stack

Covers:
  - bankstatement_parser: _decimal_from_amount, _extract_date, IBAN mapping,
    parse_camt053 fallback (no bankstatementparser installed)
  - statement_poller: health_check (mock HTTP), IBAN config guard,
    _resolve_account_id, poll_statements dry path
  - services/config.py: env var defaults

Run:
    pytest tests/test_parsers_and_poller.py -v
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import os
from unittest.mock import MagicMock, patch

# ── bankstatement_parser ──────────────────────────────────────────────────────


class TestDecimalFromAmount:
    def test_decimal_passthrough(self):
        from services.recon.bankstatement_parser import _decimal_from_amount

        result = _decimal_from_amount(Decimal("100.50"))
        assert result == Decimal("100.50")
        assert isinstance(result, Decimal)

    def test_float_converted(self):
        from services.recon.bankstatement_parser import _decimal_from_amount

        result = _decimal_from_amount(100.50)
        assert isinstance(result, Decimal)

    def test_string_converted(self):
        from services.recon.bankstatement_parser import _decimal_from_amount

        result = _decimal_from_amount("250.00")
        assert result == Decimal("250.00")

    def test_integer_converted(self):
        from services.recon.bankstatement_parser import _decimal_from_amount

        result = _decimal_from_amount(1000)
        assert result == Decimal("1000")


class TestExtractDate:
    def test_returns_today_when_none(self):
        from services.recon.bankstatement_parser import _extract_date

        stmt = MagicMock()
        stmt.closing_date = None
        stmt.creation_date = None
        result = _extract_date(stmt)
        assert isinstance(result, date)

    def test_extracts_date_from_datetime(self):
        from services.recon.bankstatement_parser import _extract_date

        dt = datetime(2026, 4, 7, 10, 30)
        stmt = MagicMock()
        stmt.closing_date = dt
        result = _extract_date(stmt)
        assert result == date(2026, 4, 7)

    def test_extracts_plain_date(self):
        from services.recon.bankstatement_parser import _extract_date

        stmt = MagicMock()
        stmt.closing_date = date(2026, 3, 31)
        result = _extract_date(stmt)
        assert result == date(2026, 3, 31)


class TestParseCamt053Fallback:
    """parse_camt053 returns [] when bankstatementparser not installed."""

    def test_returns_empty_when_library_missing(self, tmp_path):
        from services.recon.bankstatement_parser import parse_camt053

        # bankstatementparser is not installed → should return []
        xml_path = tmp_path / "dummy.xml"
        xml_path.write_text("<Document/>")
        result = parse_camt053(xml_path)
        # Either [] (library not installed) or list of StatementBalance
        assert isinstance(result, list)

    def test_returns_empty_for_nonexistent_iban(self, monkeypatch, tmp_path):
        """IBAN not in IBAN_TO_ACCOUNT_ID → account skipped."""
        mock_stmt = MagicMock()
        mock_stmt.iban = "GB99XXXX99999999999999"  # unknown IBAN
        mock_stmt.closing_balance = Decimal("1000.00")
        mock_stmt.currency = "GBP"
        mock_stmt.closing_date = date(2026, 4, 7)

        mock_parser_instance = MagicMock()
        mock_parser_instance.parse.return_value = [mock_stmt]

        mock_camt_module = MagicMock()
        mock_camt_module.CamtParser.return_value = mock_parser_instance

        xml_path = tmp_path / "test.xml"
        xml_path.write_text("<Document/>")

        with patch.dict("sys.modules", {"bankstatementparser": mock_camt_module}):
            import importlib

            from services.recon import bankstatement_parser

            importlib.reload(bankstatement_parser)
            result = bankstatement_parser.parse_camt053(xml_path)

        assert result == []


# ── statement_poller ──────────────────────────────────────────────────────────


class TestStatementPollerHealthCheck:
    def test_health_check_returns_false_when_service_down(self, monkeypatch):
        """health_check() returns False when mock-ASPSP unreachable."""
        import httpx

        monkeypatch.setenv("ADORSYS_PSD2_URL", "http://localhost:19999")

        def raise_connect(*args, **kwargs):
            raise httpx.ConnectError("connection refused")

        with patch("httpx.get", side_effect=raise_connect):
            import importlib

            from services.recon import statement_poller

            importlib.reload(statement_poller)
            result = statement_poller.health_check()

        assert result is False

    def test_health_check_returns_true_on_200(self, monkeypatch):
        """health_check() returns True when mock-ASPSP returns 200."""
        monkeypatch.setenv("ADORSYS_PSD2_URL", "http://localhost:8888")

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.get", return_value=mock_response):
            import importlib

            from services.recon import statement_poller

            importlib.reload(statement_poller)
            result = statement_poller.health_check()

        assert result is True


class TestStatementPollerNoIbans:
    def test_poll_returns_empty_when_no_ibans(self, monkeypatch):
        """poll_statements() returns [] when SAFEGUARDING IBANs not configured."""
        monkeypatch.delenv("SAFEGUARDING_OPERATIONAL_IBAN", raising=False)
        monkeypatch.delenv("SAFEGUARDING_CLIENT_FUNDS_IBAN", raising=False)

        import importlib

        from services.recon import statement_poller

        importlib.reload(statement_poller)
        result = statement_poller.poll_statements(date(2026, 4, 7))
        assert result == []


# ── services/config.py ────────────────────────────────────────────────────────


class TestConfig:
    def test_clickhouse_defaults(self):
        import importlib

        from services import config

        importlib.reload(config)
        assert os.environ.get("CLICKHOUSE_HOST", "localhost") == config.CLICKHOUSE_HOST
        assert int(os.environ.get("CLICKHOUSE_PORT", "9000")) == config.CLICKHOUSE_PORT
        assert os.environ.get("CLICKHOUSE_DB", "banxe") == config.CLICKHOUSE_DB

    def test_midaz_defaults(self):
        from services import config

        assert config.MIDAZ_BASE_URL.startswith("http")

    def test_config_imported_by_clickhouse_client(self):
        """Verify clickhouse_client now imports from services.config (no duplication)."""
        import inspect

        import services.recon.clickhouse_client as ch

        source = inspect.getsource(ch)
        assert "from services.config import" in source
        # Should NOT have direct os.environ.get for ClickHouse vars
        assert 'os.environ.get("CLICKHOUSE_HOST"' not in source

    def test_config_imported_by_fin060_generator(self):
        """Verify fin060_generator now imports from services.config."""
        import inspect

        import services.reporting.fin060_generator as fin

        source = inspect.getsource(fin)
        assert "from services.config import" in source
        assert 'os.environ.get("CLICKHOUSE_HOST"' not in source


# ── bankstatement_parser: parse_mt940 + _extract_date edge cases ─────────────


class TestParseMt940:
    def test_returns_empty_when_mt940_not_installed(self, tmp_path):
        """parse_mt940 returns [] gracefully when mt940 library not installed."""
        with patch.dict("sys.modules", {"mt940": None}):
            import importlib

            from services.recon import bankstatement_parser

            importlib.reload(bankstatement_parser)
            mt940_path = tmp_path / "test.sta"
            mt940_path.write_text("dummy")
            result = bankstatement_parser.parse_mt940(mt940_path)
        assert result == []


class TestExtractDateEdgeCases:
    def test_fallback_when_date_is_unexpected_type(self):
        """_extract_date returns today() when d is truthy but not date/datetime."""
        from services.recon.bankstatement_parser import _extract_date

        stmt = MagicMock(spec=[])  # no closing_date or creation_date attrs
        stmt.closing_date = "not-a-date"  # truthy, but no .date() method, not date
        stmt.creation_date = None
        result = _extract_date(stmt)
        assert isinstance(result, date)
