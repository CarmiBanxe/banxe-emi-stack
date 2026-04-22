"""
tests/test_recon/test_camt053_parser.py — CAMT.053 parser tests
IL-REC-01 | Phase 51B | Sprint 36
≥20 tests covering parse_camt053, CRDT/DBIT handling, generate_sample
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.recon.camt053_parser import generate_sample_camt053, parse_camt053
from services.recon.reconciliation_engine_v2 import StatementEntry


def test_parse_sample_returns_list() -> None:
    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    assert isinstance(entries, list)


def test_parse_sample_returns_three_entries() -> None:
    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    assert len(entries) == 3


def test_parse_sample_returns_statement_entries() -> None:
    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    for e in entries:
        assert isinstance(e, StatementEntry)


def test_parse_crdt_entry_positive() -> None:
    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    # TXN-001 is CRDT £1000 → positive
    crdt_entry = next(e for e in entries if e.amount == Decimal("1000.00"))
    assert crdt_entry.amount > Decimal("0")


def test_parse_dbit_entry_negative() -> None:
    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    # TXN-003 is DBIT £200 → negative
    dbit_entry = next(e for e in entries if e.amount == Decimal("-200.00"))
    assert dbit_entry.amount < Decimal("0")


def test_parse_amounts_are_decimal() -> None:
    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    for e in entries:
        assert isinstance(e.amount, Decimal)
        assert not isinstance(e.amount, float)


def test_parse_entry_has_iban() -> None:
    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    for e in entries:
        assert e.account_iban != ""


def test_parse_entry_has_entry_id() -> None:
    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    for e in entries:
        assert e.entry_id != ""
        assert len(e.entry_id) == 8


def test_parse_entry_currency_gbp() -> None:
    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    for e in entries:
        assert e.currency == "GBP"


def test_parse_entry_value_date() -> None:
    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    for e in entries:
        assert e.value_date == "2026-04-21"


def test_parse_empty_xml_returns_empty_list() -> None:
    xml_bytes = b"<Document><BkToCstmrStmt><Stmt></Stmt></BkToCstmrStmt></Document>"
    entries = parse_camt053(xml_bytes)
    assert entries == []


def test_generate_sample_returns_bytes() -> None:
    result = generate_sample_camt053()
    assert isinstance(result, bytes)


def test_generate_sample_is_valid_xml() -> None:
    import xml.etree.ElementTree as ET

    xml_bytes = generate_sample_camt053()
    # Should not raise
    ET.fromstring(xml_bytes)  # noqa: S314


def test_parse_500_50_entry() -> None:
    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    amounts = [e.amount for e in entries]
    assert Decimal("500.50") in amounts


def test_parse_1000_entry_present() -> None:
    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    amounts = [e.amount for e in entries]
    assert Decimal("1000.00") in amounts


def test_parse_negative_200_entry_present() -> None:
    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    amounts = [e.amount for e in entries]
    assert Decimal("-200.00") in amounts


def test_statement_entry_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    entry = entries[0]
    with pytest.raises(FrozenInstanceError):
        entry.amount = Decimal("999")  # type: ignore[misc]


def test_parse_multiple_ibans() -> None:
    xml_bytes = b"""<Document>
      <BkToCstmrStmt><Stmt>
        <Ntry>
          <NtryRef>T1</NtryRef><Amt Ccy="GBP">100.00</Amt>
          <CdtDbtInd>CRDT</CdtDbtInd>
          <NtryDtls><TxDtls><RltdPties><CdtrAcct><Id><IBAN>GB01</IBAN></Id></CdtrAcct></RltdPties></TxDtls></NtryDtls>
        </Ntry>
        <Ntry>
          <NtryRef>T2</NtryRef><Amt Ccy="GBP">200.00</Amt>
          <CdtDbtInd>CRDT</CdtDbtInd>
          <NtryDtls><TxDtls><RltdPties><CdtrAcct><Id><IBAN>GB02</IBAN></Id></CdtrAcct></RltdPties></TxDtls></NtryDtls>
        </Ntry>
      </Stmt></BkToCstmrStmt>
    </Document>"""
    entries = parse_camt053(xml_bytes)
    assert len(entries) == 2


def test_parse_description_captured() -> None:
    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    descriptions = [e.description for e in entries]
    assert any("Payment" in d or "deposit" in d or "deduction" in d for d in descriptions)


def test_parse_transaction_ref_captured() -> None:
    xml_bytes = generate_sample_camt053()
    entries = parse_camt053(xml_bytes)
    refs = [e.transaction_ref for e in entries]
    assert any(r != "" for r in refs)
