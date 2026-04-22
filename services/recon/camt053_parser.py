"""
services/recon/camt053_parser.py — ISO 20022 CAMT.053 XML parser
IL-REC-01 | Phase 51B | Sprint 36
Uses defusedxml for safe XML parsing (XXE/billion-laughs protected).
Invariants: I-01 (Decimal for all amounts)
"""

from __future__ import annotations

from decimal import Decimal
import hashlib
import xml.etree.ElementTree as ET

import defusedxml.ElementTree as DefusedET

from services.recon.reconciliation_engine_v2 import StatementEntry

# ISO 20022 namespace
_NS = {"camt": "urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"}


def _find_first(element: ET.Element, *paths: str) -> ET.Element | None:
    """Find the first matching element using multiple XPath candidates (None-safe)."""
    for path in paths:
        ns = _NS if "camt:" in path else {}
        result = element.find(path, ns) if ns else element.find(path)
        if result is not None:
            return result
    return None


def parse_camt053(xml_bytes: bytes) -> list[StatementEntry]:  # noqa: S314
    """
    Parse a CAMT.053 bank statement XML document.
    Returns list of StatementEntry with Decimal amounts (I-01).
    CRDT entries are positive; DBIT entries are negative.
    """
    root = DefusedET.fromstring(xml_bytes)
    entries: list[StatementEntry] = []

    # Get account IBAN from Stmt/Acct level (shared across all entries in this statement)
    stmt_iban_el = _find_first(root, ".//Acct/Id/IBAN", ".//camt:Acct/camt:Id/camt:IBAN")
    stmt_iban = stmt_iban_el.text if stmt_iban_el is not None else "UNKNOWN"

    # Iterate over all Ntry elements
    ntry_list = list(root.iter("Ntry"))
    if not ntry_list:
        # Try namespace-qualified
        ntry_list = root.findall(".//camt:Ntry", _NS)

    for ntry in ntry_list:
        entry_id_el = _find_first(ntry, "NtryRef", "camt:NtryRef")
        amt_el = _find_first(ntry, "Amt", "camt:Amt")
        cdt_dbt_el = _find_first(ntry, "CdtDbtInd", "camt:CdtDbtInd")
        val_date_el = _find_first(ntry, "ValDt/Dt", "camt:ValDt/camt:Dt", "BookgDt/Dt")
        # IBAN may be on entry level too; fall back to stmt_iban
        iban_el = _find_first(ntry, ".//IBAN", ".//camt:IBAN")
        desc_el = _find_first(ntry, ".//AddtlNtryInf", ".//camt:AddtlNtryInf")
        ref_el = _find_first(ntry, ".//EndToEndId", ".//camt:EndToEndId")

        ccy = amt_el.get("Ccy", "GBP") if amt_el is not None else "GBP"
        raw_amount = Decimal(amt_el.text or "0") if amt_el is not None else Decimal("0")
        indicator = (cdt_dbt_el.text or "CRDT").strip() if cdt_dbt_el is not None else "CRDT"
        amount = raw_amount if indicator == "CRDT" else -raw_amount

        entry_id_raw = (entry_id_el.text or "") if entry_id_el is not None else str(len(entries))
        entry_id = hashlib.sha256(entry_id_raw.encode()).hexdigest()[:8]

        iban = (iban_el.text or "UNKNOWN") if iban_el is not None else stmt_iban

        entries.append(
            StatementEntry(
                entry_id=entry_id,
                account_iban=iban,
                amount=amount,
                currency=ccy,
                value_date=(val_date_el.text or "") if val_date_el is not None else "",
                description=(desc_el.text or "") if desc_el is not None else "",
                transaction_ref=(ref_el.text or "") if ref_el is not None else "",
            )
        )

    return entries


def parse_from_file(path: str) -> list[StatementEntry]:
    """Parse CAMT.053 from a file path."""
    with open(path, "rb") as f:  # noqa: PTH123
        return parse_camt053(f.read())


def generate_sample_camt053() -> bytes:
    """Generate a sample CAMT.053 XML document for testing."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<Document>
  <BkToCstmrStmt>
    <Stmt>
      <Acct>
        <Id><IBAN>GB29NWBK60161331926819</IBAN></Id>
      </Acct>
      <Ntry>
        <NtryRef>TXN-001</NtryRef>
        <Amt Ccy="GBP">1000.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <ValDt><Dt>2026-04-21</Dt></ValDt>
        <AddtlNtryInf>Payment received from client</AddtlNtryInf>
        <NtryDtls><TxDtls><Refs><EndToEndId>E2E-001</EndToEndId></Refs></TxDtls></NtryDtls>
      </Ntry>
      <Ntry>
        <NtryRef>TXN-002</NtryRef>
        <Amt Ccy="GBP">500.50</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <ValDt><Dt>2026-04-21</Dt></ValDt>
        <AddtlNtryInf>Safeguarding deposit</AddtlNtryInf>
        <NtryDtls><TxDtls><Refs><EndToEndId>E2E-002</EndToEndId></Refs></TxDtls></NtryDtls>
      </Ntry>
      <Ntry>
        <NtryRef>TXN-003</NtryRef>
        <Amt Ccy="GBP">200.00</Amt>
        <CdtDbtInd>DBIT</CdtDbtInd>
        <ValDt><Dt>2026-04-21</Dt></ValDt>
        <AddtlNtryInf>Fee deduction</AddtlNtryInf>
        <NtryDtls><TxDtls><Refs><EndToEndId>E2E-003</EndToEndId></Refs></TxDtls></NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>"""
