"""
tests/test_compliance_kb/test_pdf_parser.py — PDF parser unit tests
IL-CKS-01 | banxe-emi-stack

Tests: 6 scenarios. No real PDF or PyMuPDF required — uses mocking.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from services.compliance_kb.ingestion.pdf_parser import (
    _extract_with_pymupdf,
    _is_heading,
    parse_pdf,
)


class TestIsHeading:
    def test_article_heading(self):
        assert _is_heading("Article 5 Safeguarding requirements") is True

    def test_chapter_heading(self):
        assert _is_heading("Chapter 3.2 Payment obligations") is True

    def test_section_heading(self):
        assert _is_heading("Section 14 AML controls") is True

    def test_numbered_heading(self):
        assert _is_heading("1. Introduction") is True

    def test_all_caps_short(self):
        assert _is_heading("ANTI-MONEY LAUNDERING REQUIREMENTS") is True

    def test_long_paragraph_not_heading(self):
        long_text = "This is a very long paragraph that cannot be a heading. " * 5
        assert _is_heading(long_text) is False

    def test_empty_not_heading(self):
        assert _is_heading("") is False

    def test_empty_whitespace_not_heading(self):
        assert _is_heading("   ") is False


class TestParsePdf:
    def test_parse_pdf_file_not_found_raises(self):
        """parse_pdf raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError, match="PDF not found"):
            parse_pdf("/nonexistent/path/doc.pdf", document_id="doc-001")

    def test_parse_pdf_uses_pymupdf_when_available(self):
        """parse_pdf calls PyMuPDF when it returns content."""
        mock_sections = [
            ("Introduction", "Introduction text about AML requirements.", 1),
            ("Article 5", "EMIs must safeguard client funds in designated accounts.", 2),
            ("Article 6", "Monthly reporting must be submitted to FCA.", 3),
        ]
        with (
            patch(
                "services.compliance_kb.ingestion.pdf_parser._extract_with_pymupdf",
                return_value=mock_sections,
            ),
            tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp,
        ):
            tmp_path = tmp.name
            try:
                chunks = parse_pdf(tmp_path, document_id="test-pdf-001")
                assert len(chunks) >= 1
                assert all(c.document_id == "test-pdf-001" for c in chunks)
            finally:
                os.unlink(tmp_path)

    def test_parse_pdf_falls_back_to_unstructured(self):
        """parse_pdf falls back to unstructured when PyMuPDF returns empty."""
        mock_sections = [
            ("Main", "Content extracted by unstructured.", 1),
        ]
        with (
            patch(
                "services.compliance_kb.ingestion.pdf_parser._extract_with_pymupdf",
                return_value=[],
            ),
            patch(
                "services.compliance_kb.ingestion.pdf_parser._extract_with_unstructured",
                return_value=mock_sections,
            ),
            tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp,
        ):
            tmp_path = tmp.name
            try:
                chunks = parse_pdf(tmp_path, document_id="test-fallback")
                assert len(chunks) >= 1
            finally:
                os.unlink(tmp_path)

    def test_parse_pdf_raises_when_no_text(self):
        """parse_pdf raises ValueError when both extractors return nothing."""
        with (
            patch(
                "services.compliance_kb.ingestion.pdf_parser._extract_with_pymupdf",
                return_value=[],
            ),
            patch(
                "services.compliance_kb.ingestion.pdf_parser._extract_with_unstructured",
                return_value=[],
            ),
            tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp,
        ):
            tmp_path = tmp.name
            try:
                with pytest.raises(ValueError, match="No text could be extracted"):
                    parse_pdf(tmp_path, document_id="empty-pdf")
            finally:
                os.unlink(tmp_path)

    def test_parse_pdf_propagates_metadata(self):
        """parse_pdf propagates metadata to all chunks."""
        mock_sections = [
            ("Section A", "Regulatory content here. " * 10, 1),
        ]
        with (
            patch(
                "services.compliance_kb.ingestion.pdf_parser._extract_with_pymupdf",
                return_value=mock_sections,
            ),
            tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp,
        ):
            tmp_path = tmp.name
            try:
                chunks = parse_pdf(
                    tmp_path,
                    document_id="doc-meta",
                    metadata={"jurisdiction": "eu", "version": "2024"},
                )
                assert all(c.metadata.get("jurisdiction") == "eu" for c in chunks)
            finally:
                os.unlink(tmp_path)


class TestExtractWithPymupdf:
    def test_extract_returns_empty_on_import_error(self):
        """Returns empty list when PyMuPDF is not installed."""
        with patch.dict("sys.modules", {"fitz": None}):
            result = _extract_with_pymupdf(Path("/tmp/nonexistent.pdf"))
            assert result == []
