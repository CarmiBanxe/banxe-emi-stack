"""
services/compliance_kb/ingestion/pdf_parser.py — PDF ingestion
IL-CKS-01 | banxe-emi-stack

Extracts text from PDF documents using PyMuPDF (fitz) with fallback to
unstructured.io for complex layouts (scanned PDFs, tables).

Handles: EBA guidelines, FATF recommendations, FCA handbooks.
Output: list of (section_name, text, page) tuples ready for chunking.
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any

from services.compliance_kb.ingestion.chunker import chunk_document_sections
from services.compliance_kb.storage.models import DocumentChunk

logger = logging.getLogger("banxe.compliance_kb.pdf_parser")


# ── Public API ─────────────────────────────────────────────────────────────


def parse_pdf(
    file_path: str,
    document_id: str,
    metadata: dict[str, Any] | None = None,
) -> list[DocumentChunk]:
    """Parse a PDF file into DocumentChunk objects.

    Tries PyMuPDF first (fast, accurate for text PDFs).
    Falls back to unstructured.io for scanned/complex PDFs.

    Args:
        file_path: Absolute path to the PDF file.
        document_id: ID to assign to all chunks.
        metadata: Extra metadata propagated to chunks.

    Returns:
        List of DocumentChunk objects, ordered by page then position.

    Raises:
        FileNotFoundError: If the PDF file does not exist.
        ValueError: If the PDF contains no extractable text.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    sections = _extract_with_pymupdf(path)
    if not sections:
        logger.warning("PyMuPDF returned no text for %s — trying unstructured", file_path)
        sections = _extract_with_unstructured(path)

    if not sections:
        raise ValueError(f"No text could be extracted from PDF: {file_path}")

    page_map = {section: page for section, _, page in sections}
    section_pairs = [(section, text) for section, text, _ in sections]

    return chunk_document_sections(
        sections=section_pairs,
        document_id=document_id,
        page_map=page_map,
        metadata=metadata,
    )


def extract_pdf_sections(file_path: str) -> list[tuple[str, str, int]]:
    """Extract (section_name, text, page) from a PDF without chunking.

    Useful for debugging and version comparison.

    Returns:
        List of (section_name, text, page_number) tuples.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    sections = _extract_with_pymupdf(path)
    if not sections:
        sections = _extract_with_unstructured(path)
    return sections


# ── PyMuPDF extractor ──────────────────────────────────────────────────────


def _extract_with_pymupdf(path: Path) -> list[tuple[str, str, int]]:
    """Extract text using PyMuPDF (fitz). Returns (section, text, page)."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        sections: list[tuple[str, str, int]] = []
        current_section = "Introduction"
        buffer_texts: list[str] = []
        current_page = 1

        for page_num, page in enumerate(doc, start=1):
            blocks = page.get_text("blocks")
            for block in blocks:
                if len(block) < 5:
                    continue
                text = block[4].strip()
                if not text:
                    continue

                # Detect section headings (short bold-like lines, caps/numbered)
                if _is_heading(text):
                    if buffer_texts:
                        sections.append(
                            (
                                current_section,
                                " ".join(buffer_texts),
                                current_page,
                            )
                        )
                        buffer_texts = []
                    current_section = text[:200]
                    current_page = page_num
                else:
                    buffer_texts.append(text)

        if buffer_texts:
            sections.append((current_section, " ".join(buffer_texts), current_page))

        doc.close()
        return sections

    except ImportError:
        logger.warning("PyMuPDF not installed — install PyMuPDF to parse PDFs")
        return []
    except Exception as exc:
        logger.warning("PyMuPDF failed for %s: %s", path, exc)
        return []


def _is_heading(text: str) -> bool:
    """Heuristic: is this line a section heading?"""
    stripped = text.strip()
    if len(stripped) > 200:
        return False
    if not stripped:
        return False
    # Numbered headings: "1.", "Article 5", "Chapter 3.2", "§ 4"
    numbered = re.match(r"^(Article|Chapter|Section|§|\d+\.)\s+\d*", stripped, re.IGNORECASE)
    if numbered:
        return True
    # ALL CAPS short line
    if stripped.isupper() and 3 <= len(stripped.split()) <= 15:
        return True
    # Title case short line
    if stripped.istitle() and 2 <= len(stripped.split()) <= 10:
        return True
    return False


# ── Unstructured.io fallback ───────────────────────────────────────────────


def _extract_with_unstructured(path: Path) -> list[tuple[str, str, int]]:
    """Extract text using unstructured.io (handles scanned PDFs)."""
    try:
        from unstructured.partition.pdf import partition_pdf

        elements = partition_pdf(str(path))
        sections: list[tuple[str, str, int]] = []
        current_section = "Main"
        buffer: list[str] = []
        current_page = 1

        for el in elements:
            el_type = type(el).__name__
            page = getattr(el.metadata, "page_number", current_page) or current_page
            text = str(el).strip()

            if el_type in ("Title", "Header"):
                if buffer:
                    sections.append((current_section, " ".join(buffer), current_page))
                    buffer = []
                current_section = text[:200]
                current_page = page
            elif text:
                buffer.append(text)

        if buffer:
            sections.append((current_section, " ".join(buffer), current_page))

        return sections

    except ImportError:
        logger.warning("unstructured not installed — install 'unstructured' for scanned PDFs")
        return []
    except Exception as exc:
        logger.warning("unstructured failed for %s: %s", path, exc)
        return []
