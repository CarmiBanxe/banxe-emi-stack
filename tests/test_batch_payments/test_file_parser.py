"""
tests/test_batch_payments/test_file_parser.py — Tests for FileParser
IL-BPP-01 | Phase 36 | 18 tests
"""

from __future__ import annotations

import hashlib

import pytest

from services.batch_payments.file_parser import FileParser
from services.batch_payments.models import FileFormat


@pytest.fixture()
def parser():
    return FileParser()


BACS_CONTENT = (
    "10-00-00|12345678|Alice Smith|10000|REF001\n20-00-00|87654321|Bob Jones|20000|REF002"
)

CSV_CONTENT = "ref,iban,name,amount,currency\nREF001,GB29NWBK60161331926819,Alice,100.00,GBP\nREF002,DE89370400440532013000,Bob,200.00,EUR"

SEPA_XML = """<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.03">
  <CstmrCdtTrfInitn>
    <PmtInf>
      <CdtTrfTxInf>
        <PmtId><EndToEndId>REF001</EndToEndId></PmtId>
        <Amt><InstdAmt Ccy="EUR">100.00</InstdAmt></Amt>
        <Cdtr><Nm>Alice</Nm></Cdtr>
        <CdtrAcct><Id><IBAN>DE89370400440532013000</IBAN></Id></CdtrAcct>
      </CdtTrfTxInf>
    </PmtInf>
  </CstmrCdtTrfInitn>
</Document>"""


def test_parse_bacs_returns_list(parser):
    records = parser.parse_bacs_std18(BACS_CONTENT)
    assert isinstance(records, list)
    assert len(records) == 2


def test_parse_bacs_fields(parser):
    records = parser.parse_bacs_std18(BACS_CONTENT)
    assert records[0]["name"] == "Alice Smith"
    assert records[0]["amount"] == "10000"


def test_parse_bacs_empty_content(parser):
    records = parser.parse_bacs_std18("")
    assert records == []


def test_parse_bacs_skips_comments(parser):
    content = "# comment\n10-00-00|12345678|Alice|10000|REF001"
    records = parser.parse_bacs_std18(content)
    assert len(records) == 1


def test_parse_sepa_pain001_returns_list(parser):
    records = parser.parse_sepa_pain001(SEPA_XML)
    assert isinstance(records, list)
    assert len(records) == 1


def test_parse_sepa_pain001_fields(parser):
    records = parser.parse_sepa_pain001(SEPA_XML)
    assert records[0]["name"] == "Alice"
    assert records[0]["iban"] == "DE89370400440532013000"
    assert records[0]["amount"] == "100.00"


def test_parse_sepa_pain001_invalid_xml(parser):
    records = parser.parse_sepa_pain001("<invalid xml>")
    assert records == []


def test_parse_csv_banxe_returns_list(parser):
    records = parser.parse_csv_banxe(CSV_CONTENT)
    assert isinstance(records, list)
    assert len(records) == 2


def test_parse_csv_banxe_fields(parser):
    records = parser.parse_csv_banxe(CSV_CONTENT)
    assert records[0]["ref"] == "REF001"
    assert records[0]["iban"] == "GB29NWBK60161331926819"
    assert records[0]["amount"] == "100.00"


def test_parse_csv_banxe_currency(parser):
    records = parser.parse_csv_banxe(CSV_CONTENT)
    assert records[0]["currency"] == "GBP"


def test_detect_format_sepa(parser):
    fmt = parser.detect_format(SEPA_XML)
    assert fmt == FileFormat.SEPA_PAIN001


def test_detect_format_csv(parser):
    fmt = parser.detect_format(CSV_CONTENT)
    assert fmt == FileFormat.CSV_BANXE


def test_detect_format_bacs(parser):
    fmt = parser.detect_format(BACS_CONTENT)
    assert fmt == FileFormat.BACS_STD18


def test_compute_file_hash_sha256(parser):
    content = "test content"
    expected = hashlib.sha256(content.encode()).hexdigest()
    assert parser.compute_file_hash(content) == expected


def test_compute_file_hash_length_64(parser):
    hash_val = parser.compute_file_hash("any content")
    assert len(hash_val) == 64


def test_validate_format_sepa_valid(parser):
    assert parser.validate_format(SEPA_XML, FileFormat.SEPA_PAIN001) is True


def test_validate_format_csv_valid(parser):
    assert parser.validate_format(CSV_CONTENT, FileFormat.CSV_BANXE) is True


def test_validate_format_bacs_valid(parser):
    assert parser.validate_format(BACS_CONTENT, FileFormat.BACS_STD18) is True
