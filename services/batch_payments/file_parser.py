"""
services/batch_payments/file_parser.py — Payment file format parsing
IL-BPP-01 | Phase 36 | banxe-emi-stack
I-12: SHA-256 file integrity hash.
"""

from __future__ import annotations

import csv
import hashlib
import io
import xml.etree.ElementTree as ET

from services.batch_payments.models import FileFormat


class FileParser:
    """Parse payment files in Bacs, SEPA, CSV, and SWIFT formats."""

    def parse_bacs_std18(self, content: str) -> list[dict[str, str]]:
        """Parse Bacs Standard 18 fixed-width format."""
        records = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) >= 4:
                records.append(
                    {
                        "sort_code": parts[0].strip(),
                        "account": parts[1].strip(),
                        "name": parts[2].strip(),
                        "amount": parts[3].strip(),
                        "ref": parts[4].strip() if len(parts) > 4 else "",
                    }
                )
        return records

    def parse_sepa_pain001(self, content: str) -> list[dict[str, str]]:
        """Parse SEPA pain.001 XML using stdlib xml.etree."""
        records = []
        try:
            root = ET.fromstring(content)  # noqa: S314  # nosec B314
            ns = {"s": "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"}
            for txn in root.findall(".//s:CdtTrfTxInf", ns):
                iban_el = txn.find(".//s:IBAN", ns)
                name_el = txn.find(".//s:Nm", ns)
                amt_el = txn.find(".//s:InstdAmt", ns)
                ref_el = txn.find(".//s:EndToEndId", ns)
                records.append(
                    {
                        "iban": iban_el.text if iban_el is not None else "",
                        "name": name_el.text if name_el is not None else "",
                        "amount": amt_el.text if amt_el is not None else "0",
                        "currency": amt_el.attrib.get("Ccy", "EUR")
                        if amt_el is not None
                        else "EUR",
                        "ref": ref_el.text if ref_el is not None else "",
                    }
                )
        except ET.ParseError:
            pass
        return records

    def parse_csv_banxe(self, content: str) -> list[dict[str, str]]:
        """Parse Banxe CSV format: ref,iban,name,amount,currency."""
        records = []
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            records.append(
                {
                    "ref": row.get("ref", "").strip(),
                    "iban": row.get("iban", "").strip(),
                    "name": row.get("name", "").strip(),
                    "amount": row.get("amount", "0").strip(),
                    "currency": row.get("currency", "GBP").strip(),
                }
            )
        return records

    def detect_format(self, content: str) -> FileFormat:
        """Auto-detect file format from content."""
        stripped = content.strip()
        if stripped.startswith("<") and "pain.001" in stripped:
            return FileFormat.SEPA_PAIN001
        if stripped.startswith("<") and "MT103" in stripped:
            return FileFormat.SWIFT_MT103
        if "ref,iban" in stripped[:50].lower() or "ref" in stripped[:50].lower():
            first_line = stripped.split("\n")[0].lower()
            if "," in first_line and any(k in first_line for k in ("ref", "iban", "amount")):
                return FileFormat.CSV_BANXE
        if "|" in stripped[:100]:
            return FileFormat.BACS_STD18
        return FileFormat.CSV_BANXE

    def compute_file_hash(self, content: str) -> str:
        """SHA-256 hex hash of file content (I-12)."""
        return hashlib.sha256(content.encode()).hexdigest()

    def validate_format(self, content: str, file_format: FileFormat) -> bool:
        """Validate content matches expected format."""
        stripped = content.strip()
        if file_format == FileFormat.SEPA_PAIN001:
            return stripped.startswith("<") and "pain.001" in stripped
        if file_format == FileFormat.SWIFT_MT103:
            return "MT103" in stripped or stripped.startswith("{1:")
        if file_format == FileFormat.BACS_STD18:
            return "|" in stripped
        if file_format == FileFormat.CSV_BANXE:
            return "," in stripped
        return False
