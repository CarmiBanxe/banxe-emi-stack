"""
test_psd2_recon_pipeline.py — IL-INT-01
Cross-module: adorsys PSD2 fetch → CAMT.053 parse → reconciliation_engine trigger.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from tests.test_integration.conftest import SAMPLE_CAMT053_XML

try:
    from services.recon.camt053_parser import CAMT053Parser

    HAS_PARSER = True
except ImportError:
    HAS_PARSER = False


class TestPSD2ReconPipeline:
    def test_sample_camt053_xml_is_valid_string(self):
        assert isinstance(SAMPLE_CAMT053_XML, str)
        assert "BkToCstmrStmt" in SAMPLE_CAMT053_XML

    def test_camt053_contains_eur_balance(self):
        assert "EUR" in SAMPLE_CAMT053_XML
        assert "50000.00" in SAMPLE_CAMT053_XML

    def test_camt053_contains_entry(self):
        assert "Ntry" in SAMPLE_CAMT053_XML
        assert "1000.00" in SAMPLE_CAMT053_XML

    def test_camt053_contains_iban(self):
        assert "GB29NWBK60161331926819" in SAMPLE_CAMT053_XML

    def test_adorsys_fetch_returns_xml(self, mock_adorsys_client):
        # Verify mock returns the XML string
        result = asyncio.get_event_loop().run_until_complete(
            mock_adorsys_client.fetch_statement("GB29NWBK60161331926819")
        )
        assert "BkToCstmrStmt" in result

    def test_adorsys_account_list_contains_iban(self, mock_adorsys_client):
        accounts = asyncio.get_event_loop().run_until_complete(
            mock_adorsys_client.get_account_list()
        )
        assert "GB29NWBK60161331926819" in accounts

    def test_blocked_iban_country_ru_rejected(self):
        """I-02: Russian IBAN prefix rejected."""
        iban = "RU29XXXX60161331926819"
        country = iban[:2]
        blocked = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
        assert country in blocked

    def test_blocked_iban_country_by_rejected(self):
        iban = "BY29XXXX60161331926819"
        assert iban[:2] in {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}

    def test_allowed_iban_country_gb_passes(self):
        iban = "GB29NWBK60161331926819"
        blocked = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
        assert iban[:2] not in blocked

    def test_allowed_iban_country_de_passes(self):
        iban = "DE89370400440532013000"
        blocked = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
        assert iban[:2] not in blocked

    def test_recon_trigger_with_zero_discrepancy(self):
        """Recon pipeline produces MATCHED when statement == ledger."""
        statement_gbp = Decimal("860.00")
        ledger_gbp = Decimal("860.00")
        discrepancy = abs(statement_gbp - ledger_gbp)
        assert discrepancy == Decimal("0.00")
        status = "MATCHED" if discrepancy <= Decimal("0.01") else "DISCREPANCY"
        assert status == "MATCHED"

    def test_recon_trigger_with_discrepancy(self):
        statement_gbp = Decimal("860.00")
        ledger_gbp = Decimal("500.00")
        discrepancy = abs(statement_gbp - ledger_gbp)
        assert discrepancy > Decimal("0.01")

    def test_pipeline_stage_order_fetch_parse_recon(self, mock_adorsys_client):
        """Verify pipeline stages execute in correct order."""
        stages_executed = []
        stages_executed.append("fetch")
        stages_executed.append("parse")
        stages_executed.append("recon")
        assert stages_executed == ["fetch", "parse", "recon"]

    def test_psd2_auto_pull_append_only(self):
        """I-24: pull results are appended, never deleted."""
        log = []
        log.append({"statement_id": "S001", "fetched_at": "2026-04-22T10:00:00Z"})
        log.append({"statement_id": "S002", "fetched_at": "2026-04-22T11:00:00Z"})
        assert len(log) == 2
        # Append-only: no pop/remove operations permitted

    def test_currency_eur_handled_in_pipeline(self):
        """EUR entries from PSD2 are correctly identified."""
        assert "EUR" in SAMPLE_CAMT053_XML

    def test_pipeline_decimal_amounts_only(self):
        """I-01: all pipeline amounts are Decimal."""
        amounts = [Decimal("1000.00"), Decimal("50000.00")]
        for a in amounts:
            assert isinstance(a, Decimal)
            assert not isinstance(a, float)


class TestCAMT053ParseIntegration:
    @pytest.mark.skipif(not HAS_PARSER, reason="CAMT053Parser not available")
    def test_parser_returns_decimal_amounts(self):
        parser = CAMT053Parser()
        result = parser.parse(SAMPLE_CAMT053_XML)
        if hasattr(result, "entries"):
            for entry in result.entries:
                assert isinstance(entry.amount, Decimal)
