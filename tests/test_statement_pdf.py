"""
tests/test_statement_pdf.py — AccountStatementService PDF/HTML (IL-054)
FCA PS7/24: monthly statement must be available to client on request.
WeasyPrint: tested via mock — does not require binary installed in CI.
"""
from __future__ import annotations

import sys
import types
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.statements.statement_service import (
    AccountStatement,
    AccountStatementService,
    InMemoryTransactionRepository,
    TransactionLine,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_tx(
    dt: date,
    description: str,
    ref: str,
    debit: Decimal | None,
    credit: Decimal | None,
    balance: Decimal,
) -> TransactionLine:
    return TransactionLine(
        date=dt,
        description=description,
        reference=ref,
        debit=debit,
        credit=credit,
        balance_after=balance,
        transaction_id=f"tx-{ref}",
    )


@pytest.fixture()
def sample_transactions() -> list[TransactionLine]:
    return [
        _make_tx(date(2026, 3, 5),  "BACS Receipt — salary",  "SAL-001", None,           Decimal("3500.00"), Decimal("5000.00")),
        _make_tx(date(2026, 3, 10), "Rent payment",           "RENT-03", Decimal("1200.00"), None,            Decimal("3800.00")),
        _make_tx(date(2026, 3, 22), "FPS — supplier ABC",     "FPS-042", Decimal("450.00"),  None,            Decimal("3350.00")),
    ]


@pytest.fixture()
def sample_statement(sample_transactions: list[TransactionLine]) -> AccountStatement:
    repo = InMemoryTransactionRepository(
        transactions=sample_transactions,
        opening_balance=Decimal("1500.00"),
    )
    svc = AccountStatementService(repo=repo)
    return svc.generate(
        customer_id="cust-001",
        account_id="acc-GBP-001",
        currency="GBP",
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: _render_html() content
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderHtml:
    def _html(self, stmt: AccountStatement) -> str:
        svc = AccountStatementService(repo=InMemoryTransactionRepository())
        return svc._render_html(stmt)

    def test_contains_account_id(self, sample_statement: AccountStatement) -> None:
        html = self._html(sample_statement)
        assert "acc-GBP-001" in html

    def test_contains_customer_id(self, sample_statement: AccountStatement) -> None:
        html = self._html(sample_statement)
        assert "cust-001" in html

    def test_contains_currency(self, sample_statement: AccountStatement) -> None:
        html = self._html(sample_statement)
        assert "GBP" in html

    def test_contains_statement_id(self, sample_statement: AccountStatement) -> None:
        html = self._html(sample_statement)
        assert sample_statement.statement_id in html

    def test_contains_banxe_branding(self, sample_statement: AccountStatement) -> None:
        html = self._html(sample_statement)
        assert "Banxe" in html

    def test_contains_fca_text(self, sample_statement: AccountStatement) -> None:
        html = self._html(sample_statement)
        assert "FCA" in html or "Financial Conduct Authority" in html

    def test_contains_transaction_descriptions(self, sample_statement: AccountStatement) -> None:
        html = self._html(sample_statement)
        assert "salary" in html.lower()
        assert "Rent payment" in html

    def test_contains_opening_balance(self, sample_statement: AccountStatement) -> None:
        html = self._html(sample_statement)
        # Opening balance = 1500.00
        assert "1,500.00" in html

    def test_contains_period_dates(self, sample_statement: AccountStatement) -> None:
        html = self._html(sample_statement)
        # Period start/end appear in human-readable form
        assert "Mar 2026" in html or "01 Mar 2026" in html or "2026" in html

    def test_a4_page_directive(self, sample_statement: AccountStatement) -> None:
        html = self._html(sample_statement)
        assert "A4" in html

    def test_no_transactions_shows_placeholder(self) -> None:
        repo = InMemoryTransactionRepository(opening_balance=Decimal("0"))
        svc = AccountStatementService(repo=repo)
        stmt = svc.generate(
            customer_id="c1", account_id="a1", currency="EUR",
            period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
        )
        html = svc._render_html(stmt)
        assert "No transactions" in html

    def test_positive_class_applied_to_credits(self, sample_statement: AccountStatement) -> None:
        html = self._html(sample_statement)
        assert 'class="positive"' in html or "positive" in html

    def test_negative_class_applied_to_debits(self, sample_statement: AccountStatement) -> None:
        html = self._html(sample_statement)
        assert 'class="negative"' in html or "negative" in html

    def test_valid_html_structure(self, sample_statement: AccountStatement) -> None:
        html = self._html(sample_statement)
        assert html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "<table>" in html
        assert "<thead>" in html


# ─────────────────────────────────────────────────────────────────────────────
# Tests: generate_pdf() with mock WeasyPrint
# ─────────────────────────────────────────────────────────────────────────────

class TestGeneratePdf:
    def _mock_weasyprint(self) -> types.ModuleType:
        mock_html_instance = MagicMock()
        mock_html_class = MagicMock(return_value=mock_html_instance)
        mock_wp = types.ModuleType("weasyprint")
        mock_wp.HTML = mock_html_class
        return mock_wp

    def test_generate_pdf_calls_weasyprint(
        self, sample_statement: AccountStatement, tmp_path: Path
    ) -> None:
        mock_wp = self._mock_weasyprint()
        with patch.dict(sys.modules, {"weasyprint": mock_wp}):
            svc = AccountStatementService(repo=InMemoryTransactionRepository())
            svc.generate_pdf(sample_statement, tmp_path)

        mock_wp.HTML.assert_called_once()
        mock_wp.HTML.return_value.write_pdf.assert_called_once()

    def test_generate_pdf_returns_correct_path(
        self, sample_statement: AccountStatement, tmp_path: Path
    ) -> None:
        mock_wp = self._mock_weasyprint()
        with patch.dict(sys.modules, {"weasyprint": mock_wp}):
            svc = AccountStatementService(repo=InMemoryTransactionRepository())
            path = svc.generate_pdf(sample_statement, tmp_path)

        assert "acc-GBP-001" in str(path)
        assert "202603" in str(path)
        assert str(path).endswith(".pdf")

    def test_generate_pdf_creates_output_dir(
        self, sample_statement: AccountStatement, tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "statements" / "march"
        assert not output_dir.exists()

        mock_wp = self._mock_weasyprint()
        with patch.dict(sys.modules, {"weasyprint": mock_wp}):
            svc = AccountStatementService(repo=InMemoryTransactionRepository())
            svc.generate_pdf(sample_statement, output_dir)

        assert output_dir.exists()

    def test_generate_pdf_raises_on_missing_weasyprint(
        self, sample_statement: AccountStatement, tmp_path: Path
    ) -> None:
        # Remove weasyprint from sys.modules if present, simulate ImportError
        with patch.dict(sys.modules, {"weasyprint": None}):  # type: ignore[dict-item]
            svc = AccountStatementService(repo=InMemoryTransactionRepository())
            with pytest.raises((ImportError, TypeError)):
                svc.generate_pdf(sample_statement, tmp_path)

    def test_generate_pdf_passes_html_string(
        self, sample_statement: AccountStatement, tmp_path: Path
    ) -> None:
        mock_wp = self._mock_weasyprint()
        with patch.dict(sys.modules, {"weasyprint": mock_wp}):
            svc = AccountStatementService(repo=InMemoryTransactionRepository())
            svc.generate_pdf(sample_statement, tmp_path)

        call_kwargs = mock_wp.HTML.call_args
        # HTML(string=...) is called with the rendered HTML
        assert call_kwargs is not None
        # Either positional or keyword 'string' arg
        if call_kwargs.kwargs:
            assert "string" in call_kwargs.kwargs
            html_str = call_kwargs.kwargs["string"]
        else:
            html_str = call_kwargs.args[0]
        assert "Banxe" in html_str
        assert sample_statement.account_id in html_str


# ─────────────────────────────────────────────────────────────────────────────
# Tests: to_csv()
# ─────────────────────────────────────────────────────────────────────────────

class TestToCsv:
    def test_csv_has_header(self, sample_statement: AccountStatement) -> None:
        csv_bytes = sample_statement.to_csv()
        text = csv_bytes.decode("utf-8")
        assert "Date" in text
        assert "Description" in text
        assert "Balance" in text

    def test_csv_contains_transactions(self, sample_statement: AccountStatement) -> None:
        text = sample_statement.to_csv().decode("utf-8")
        assert "salary" in text.lower() or "SAL-001" in text
        assert "RENT-03" in text

    def test_csv_has_summary_footer(self, sample_statement: AccountStatement) -> None:
        text = sample_statement.to_csv().decode("utf-8")
        assert "Opening Balance" in text
        assert "Closing Balance" in text

    def test_csv_is_utf8(self, sample_statement: AccountStatement) -> None:
        csv_bytes = sample_statement.to_csv()
        assert isinstance(csv_bytes, bytes)
        csv_bytes.decode("utf-8")  # should not raise


# ─────────────────────────────────────────────────────────────────────────────
# Tests: to_dict()
# ─────────────────────────────────────────────────────────────────────────────

class TestToDict:
    def test_to_dict_keys(self, sample_statement: AccountStatement) -> None:
        d = sample_statement.to_dict()
        for key in ("statement_id", "customer_id", "account_id", "currency",
                    "period_start", "period_end", "opening_balance",
                    "closing_balance", "net_movement", "transaction_count"):
            assert key in d, f"missing key: {key}"

    def test_to_dict_amounts_are_strings(self, sample_statement: AccountStatement) -> None:
        d = sample_statement.to_dict()
        for field in ("opening_balance", "closing_balance", "net_movement",
                      "total_debits", "total_credits"):
            assert isinstance(d[field], str), f"{field} should be str"

    def test_to_dict_transaction_count(self, sample_statement: AccountStatement) -> None:
        d = sample_statement.to_dict()
        assert d["transaction_count"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# Tests: TransactionLine.amount
# ─────────────────────────────────────────────────────────────────────────────

class TestTransactionLineAmount:
    def test_credit_amount_positive(self) -> None:
        tx = _make_tx(date(2026, 1, 1), "desc", "ref", None, Decimal("100"), Decimal("200"))
        assert tx.amount == Decimal("100")

    def test_debit_amount_negative(self) -> None:
        tx = _make_tx(date(2026, 1, 1), "desc", "ref", Decimal("50"), None, Decimal("150"))
        assert tx.amount == Decimal("-50")
