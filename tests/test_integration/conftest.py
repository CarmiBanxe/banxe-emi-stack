"""Shared fixtures for cross-module integration tests (IL-INT-01)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Frankfurter mock ─────────────────────────────────────────────────────────


@pytest.fixture
def mock_frankfurter_rates():
    """Returns EUR/GBP = 0.86 and USD/GBP = 0.79 as Decimal."""
    return {
        "EUR": Decimal("0.8600"),
        "USD": Decimal("0.7900"),
        "GBP": Decimal("1.0000"),
    }


@pytest.fixture
def mock_frankfurter_client(mock_frankfurter_rates):
    client = MagicMock()

    async def _get_rate(base: str, target: str) -> Decimal:
        key = f"{base}/{target}"
        mapping = {
            "EUR/GBP": Decimal("0.8600"),
            "USD/GBP": Decimal("0.7900"),
            "GBP/EUR": Decimal("1.1628"),
            "GBP/USD": Decimal("1.2658"),
            "GBP/GBP": Decimal("1.0000"),
        }
        return mapping.get(key, Decimal("1.0000"))

    client.get_rate = _get_rate
    return client


# ── adorsys/PSD2 mock ────────────────────────────────────────────────────────
SAMPLE_CAMT053_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <GrpHdr><MsgId>MSG001</MsgId><CreDtTm>2026-04-22T10:00:00</CreDtTm></GrpHdr>
    <Stmt>
      <Id>STMT001</Id>
      <Acct><Id><IBAN>GB29NWBK60161331926819</IBAN></Id><Ccy>EUR</Ccy></Acct>
      <Bal>
        <Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="EUR">50000.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <Dt><Dt>2026-04-22</Dt></Dt>
      </Bal>
      <Ntry>
        <Amt Ccy="EUR">1000.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <Sts>BOOK</Sts>
        <BookgDt><Dt>2026-04-22</Dt></BookgDt>
        <NtryDtls><TxDtls><Refs><EndToEndId>E2E001</EndToEndId></Refs></TxDtls></NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>"""


@pytest.fixture
def mock_adorsys_client():
    client = MagicMock()
    client.fetch_statement = AsyncMock(return_value=SAMPLE_CAMT053_XML)
    client.get_account_list = AsyncMock(return_value=["GB29NWBK60161331926819"])
    return client


# ── ClickHouse mock ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_clickhouse():
    ch = MagicMock()
    ch.execute = MagicMock(return_value=None)
    ch.query = MagicMock(return_value=[])
    return ch


# ── Common financial fixtures ────────────────────────────────────────────────


@pytest.fixture
def sample_amounts_decimal():
    """Always Decimal, never float (I-01)."""
    return {
        "small": Decimal("100.00"),
        "medium": Decimal("5000.00"),
        "large": Decimal("50000.00"),
        "edd_threshold": Decimal("10000.00"),
        "tolerance": Decimal("0.01"),
    }
