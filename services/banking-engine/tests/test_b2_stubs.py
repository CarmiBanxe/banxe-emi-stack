"""
B-2 sandbox unit tests — pure in-memory, no network.

Verifies:
  1. AdorsysPsd2Stub returns CAMT.053-shaped dict with test-data flag.
  2. McpLedgerStub returns synthetic ledger/CRM data with test-data flag.
  3. EgressSession attaches X-Request-ID; log_egress writes to log file.

Note: services/banking-engine uses a hyphen, so we load modules via
importlib.util to avoid the Python import restriction on hyphens.
"""

from __future__ import annotations

from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import sys
import types

_BE_ROOT = Path(__file__).parents[1]  # services/banking-engine/


def _load(relative: str) -> types.ModuleType:
    """Load a module from banking-engine by file path."""
    spec = importlib.util.spec_from_file_location(
        relative.replace("/", ".").removesuffix(".py"),
        _BE_ROOT / relative,
    )
    assert spec and spec.loader, f"Cannot find module: {relative}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# Lazy module references (loaded once per session)
_adorsys_mod = _load("stubs/adorsys_psd2_stub.py")
_mcp_mod = _load("stubs/mcp_ledger_stub.py")
_egress_mod = _load("egress_logger.py")

AdorsysPsd2Stub = _adorsys_mod.AdorsysPsd2Stub
McpLedgerStub = _mcp_mod.McpLedgerStub
EgressSession = _egress_mod.EgressSession
log_egress = _egress_mod.log_egress


# ---------------------------------------------------------------------------
# AdorsysPsd2Stub
# ---------------------------------------------------------------------------


class TestAdorsysPsd2Stub:
    def setup_method(self) -> None:
        self.stub = AdorsysPsd2Stub()

    def test_returns_camt053_document_type(self) -> None:
        result = self.stub.get_camt053_statement()
        assert result["document_type"] == "CAMT.053"

    def test_is_test_data_flag_set(self) -> None:
        result = self.stub.get_camt053_statement()
        assert result["is_test_data"] is True

    def test_statement_has_entries(self) -> None:
        result = self.stub.get_camt053_statement()
        assert len(result["statement"]["entries"]) >= 1

    def test_entries_carry_test_data_flag(self) -> None:
        for entry in self.stub.get_camt053_statement()["statement"]["entries"]:
            assert entry["is_test_data"] is True

    def test_fake_iban_starts_with_test(self) -> None:
        iban = self.stub.get_camt053_statement()["statement"]["account"]["iban"]
        assert iban.startswith("TEST")

    def test_balances_are_valid_decimal_strings(self) -> None:
        stmt = self.stub.get_camt053_statement()["statement"]
        assert Decimal(stmt["opening_balance"]["amount"]) > 0
        assert Decimal(stmt["closing_balance"]["amount"]) > 0

    def test_group_header_has_message_id(self) -> None:
        assert "message_id" in self.stub.get_camt053_statement()["group_header"]

    def test_schema_version_present(self) -> None:
        assert "schema_version" in self.stub.get_camt053_statement()


# ---------------------------------------------------------------------------
# McpLedgerStub
# ---------------------------------------------------------------------------


class TestMcpLedgerStub:
    def setup_method(self) -> None:
        self.stub = McpLedgerStub()

    def test_get_balance_is_test_data(self) -> None:
        assert self.stub.get_balance()["is_test_data"] is True

    def test_get_balance_decimal_string(self) -> None:
        assert Decimal(self.stub.get_balance()["balance"]) >= 0

    def test_list_transactions_returns_list(self) -> None:
        txs = self.stub.list_transactions()
        assert isinstance(txs, list) and len(txs) >= 1

    def test_transactions_carry_test_data_flag(self) -> None:
        for tx in self.stub.list_transactions():
            assert tx["is_test_data"] is True

    def test_transaction_amounts_are_decimal_strings(self) -> None:
        for tx in self.stub.list_transactions():
            assert Decimal(tx["amount"]) > 0

    def test_create_transaction_posted(self) -> None:
        result = self.stub.create_transaction(
            account_id="TEST-ACC-0001",
            amount=Decimal("100.00"),
            currency="GBP",
            direction="credit",
            narrative="TEST",
        )
        assert result["status"] == "posted"
        assert result["is_test_data"] is True

    def test_get_customer_is_test_data(self) -> None:
        assert self.stub.get_customer()["is_test_data"] is True

    def test_get_customer_has_kyc_status(self) -> None:
        assert "kyc_status" in self.stub.get_customer()


# ---------------------------------------------------------------------------
# EgressSession / egress_logger
# ---------------------------------------------------------------------------


class TestEgressLogger:
    def test_prepare_headers_returns_x_request_id(self) -> None:
        session = EgressSession()
        rid, headers = session.prepare_headers()
        assert "X-Request-ID" in headers
        assert headers["X-Request-ID"] == rid

    def test_prepare_headers_custom_rid(self) -> None:
        session = EgressSession()
        rid, headers = session.prepare_headers(request_id="custom-001")
        assert rid == "custom-001"
        assert headers["X-Request-ID"] == "custom-001"

    def test_log_egress_appends_record(self, tmp_path: Path) -> None:
        _egress_mod._EGRESS_LOG_PATH = tmp_path / "egress.jsonl"

        log_egress(
            request_id="rid-001",
            method="GET",
            url="https://api.example.com/v1/res?secret=STRIP_ME",
            status_code=200,
        )

        lines = (tmp_path / "egress.jsonl").read_text().strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["request_id"] == "rid-001"
        assert record["method"] == "GET"
        assert record["status_code"] == 200
        assert "STRIP_ME" not in record["url"]
        assert "secret" not in record["url"]

    def test_log_egress_appends_multiple(self, tmp_path: Path) -> None:
        _egress_mod._EGRESS_LOG_PATH = tmp_path / "multi.jsonl"
        for i in range(3):
            log_egress(
                request_id=f"rid-{i}",
                method="POST",
                url=f"https://bank.test/v1/tx/{i}",
                status_code=201,
            )
        lines = (tmp_path / "multi.jsonl").read_text().strip().split("\n")
        assert len(lines) == 3

    def test_session_log_writes_record(self, tmp_path: Path) -> None:
        _egress_mod._EGRESS_LOG_PATH = tmp_path / "session.jsonl"
        session = EgressSession()
        rid, _ = session.prepare_headers()
        session.log(rid, "GET", "https://psd2.test/accounts", status_code=200)
        record = json.loads((tmp_path / "session.jsonl").read_text().strip())
        assert record["request_id"] == rid
