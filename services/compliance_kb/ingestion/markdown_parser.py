"""
services/compliance_kb/ingestion/markdown_parser.py — Markdown ingestion
IL-CKS-01 | banxe-emi-stack

Parses .md / .mdx files into (section_name, text) pairs, then chunks them.
Supports ATX headings (# H1, ## H2) and setext headings.
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any

from services.compliance_kb.ingestion.chunker import chunk_document_sections
from services.compliance_kb.storage.models import DocumentChunk

logger = logging.getLogger("banxe.compliance_kb.markdown_parser")

# ATX heading pattern: # Title, ## Sub, ### Sub-sub
_ATX_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
# Setext heading: underline with === or ---
_SETEXT_H1 = re.compile(r"^=+\s*$")
_SETEXT_H2 = re.compile(r"^-{2,}\s*$")


# ── Public API ─────────────────────────────────────────────────────────────


def parse_markdown(
    file_path: str,
    document_id: str,
    metadata: dict[str, Any] | None = None,
) -> list[DocumentChunk]:
    """Parse a Markdown file into DocumentChunk objects.

    Args:
        file_path: Path to the .md or .mdx file.
        document_id: ID to assign to all chunks.
        metadata: Extra metadata propagated to chunks.

    Returns:
        List of DocumentChunk objects.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Markdown file not found: {file_path}")

    text = path.read_text(encoding="utf-8")
    sections = extract_markdown_sections(text)

    if not sections:
        # Treat the whole file as one section
        sections = [("Main", text)]

    return chunk_document_sections(
        sections=sections,
        document_id=document_id,
        metadata=metadata,
    )


def parse_markdown_text(
    text: str,
    document_id: str,
    metadata: dict[str, Any] | None = None,
) -> list[DocumentChunk]:
    """Parse raw markdown text (no file) into DocumentChunk objects."""
    sections = extract_markdown_sections(text)
    if not sections:
        sections = [("Main", text)]
    return chunk_document_sections(
        sections=sections,
        document_id=document_id,
        metadata=metadata,
    )


def extract_markdown_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown text into (heading, body) pairs.

    Returns an empty list if no headings are found.
    """
    lines = text.splitlines()
    sections: list[tuple[str, str]] = []
    current_heading = "Introduction"
    buffer: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check for setext heading (underline on next line)
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            if _SETEXT_H1.match(next_line) and line.strip():
                _flush(sections, current_heading, buffer)
                current_heading = line.strip()
                buffer = []
                i += 2
                continue
            if _SETEXT_H2.match(next_line) and line.strip():
                _flush(sections, current_heading, buffer)
                current_heading = line.strip()
                buffer = []
                i += 2
                continue

        # Check for ATX heading
        m = _ATX_HEADING.match(line)
        if m:
            _flush(sections, current_heading, buffer)
            current_heading = m.group(2).strip()
            buffer = []
        else:
            # Strip inline code fences for embedding (keep text)
            cleaned = _strip_code_fence(line)
            buffer.append(cleaned)

        i += 1

    _flush(sections, current_heading, buffer)
    return [(h, t) for h, t in sections if t.strip()]


# ── Helpers ────────────────────────────────────────────────────────────────


def _flush(
    sections: list[tuple[str, str]],
    heading: str,
    buffer: list[str],
) -> None:
    text = "\n".join(buffer).strip()
    if text:
        sections.append((heading, text))


def _strip_code_fence(line: str) -> str:
    """Remove backtick code fences; keep the line text."""
    return re.sub(r"```\w*", "", line).strip("`").strip()
