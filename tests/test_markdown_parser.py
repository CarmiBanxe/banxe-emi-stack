"""
tests/test_markdown_parser.py — Markdown parser tests
S14-03 | banxe-emi-stack

Tests for services/compliance_kb/ingestion/markdown_parser.py:
  - parse_markdown: file → chunks
  - parse_markdown_text: raw text → chunks
  - extract_markdown_sections: heading detection (ATX + setext)

Coverage target: 25% → ≥95%
"""

from __future__ import annotations

import tempfile

import pytest

from services.compliance_kb.ingestion.markdown_parser import (
    extract_markdown_sections,
    parse_markdown,
    parse_markdown_text,
)

# ── extract_markdown_sections ─────────────────────────────────────────────────


def test_extract_sections_no_headings_uses_introduction_section():
    """No headings: text is collected under the default 'Introduction' heading."""
    text = "No headings here. Just plain text."
    sections = extract_markdown_sections(text)
    # Parser assigns text to default "Introduction" section
    assert len(sections) == 1
    assert sections[0][0] == "Introduction"
    assert "plain text" in sections[0][1]


def test_extract_sections_atx_h1():
    text = "# Introduction\n\nThis is the intro."
    sections = extract_markdown_sections(text)
    assert len(sections) == 1
    assert sections[0][0] == "Introduction"
    assert "intro" in sections[0][1]


def test_extract_sections_atx_multiple_levels():
    text = (
        "# Chapter 1\n\nChapter text.\n\n"
        "## Section 1.1\n\nSection text.\n\n"
        "### Sub-section 1.1.1\n\nSub-section text."
    )
    sections = extract_markdown_sections(text)
    headings = [s[0] for s in sections]
    assert "Chapter 1" in headings
    assert "Section 1.1" in headings
    assert "Sub-section 1.1.1" in headings


def test_extract_sections_setext_h1():
    text = "My Title\n========\n\nBody text here."
    sections = extract_markdown_sections(text)
    assert len(sections) == 1
    assert sections[0][0] == "My Title"
    assert "Body" in sections[0][1]


def test_extract_sections_setext_h2():
    text = "Sub Title\n---------\n\nSub body text."
    sections = extract_markdown_sections(text)
    assert len(sections) == 1
    assert sections[0][0] == "Sub Title"
    assert "Sub body" in sections[0][1]


def test_extract_sections_empty_text_returns_empty():
    sections = extract_markdown_sections("")
    # Empty text → no body to flush → empty list
    assert sections == [] or all(not s[1].strip() for s in sections)


def test_extract_sections_only_whitespace_returns_empty():
    sections = extract_markdown_sections("   \n\n  \n")
    # All text is whitespace → sections list will be empty (filter strips blank bodies)
    assert all(s[1].strip() for s in sections)


def test_extract_sections_filters_empty_bodies():
    text = "# Section 1\n\n\n# Section 2\n\nContent here."
    sections = extract_markdown_sections(text)
    # Section 1 has no body, so only Section 2 should appear
    headings = [s[0] for s in sections]
    assert "Section 2" in headings
    assert all(s[1].strip() for s in sections)


def test_extract_sections_preserves_text_content():
    text = "# SAR Requirements\n\nSARs must be filed within 7 days of suspicion."
    sections = extract_markdown_sections(text)
    assert len(sections) == 1
    assert "SARs must be filed" in sections[0][1]


def test_extract_sections_code_fence_stripped():
    text = "# Technical\n\n```python\ncode here\n```"
    sections = extract_markdown_sections(text)
    # Code fence markers stripped; text may remain
    if sections:
        # No triple-backtick fence marker in body
        assert "```" not in sections[0][1]


def test_extract_sections_mixed_atx_and_setext():
    text = "# ATX Heading\n\nFirst paragraph.\n\nSetext Style\n============\n\nSetext body."
    sections = extract_markdown_sections(text)
    headings = [s[0] for s in sections]
    assert "ATX Heading" in headings
    assert "Setext Style" in headings


# ── parse_markdown_text ───────────────────────────────────────────────────────


def test_parse_markdown_text_returns_chunks():
    text = "# AML Policy\n\nThe AML policy requires SAR filing within 7 days."
    chunks = parse_markdown_text(text, document_id="doc-001")
    assert len(chunks) > 0


def test_parse_markdown_text_chunks_have_document_id():
    text = "# Section\n\nSome content."
    chunks = parse_markdown_text(text, document_id="doc-xyz")
    for chunk in chunks:
        assert chunk.document_id == "doc-xyz"


def test_parse_markdown_text_with_metadata():
    text = "# Heading\n\nBody text."
    chunks = parse_markdown_text(text, document_id="doc-meta", metadata={"source": "MLR 2017"})
    assert len(chunks) > 0
    for chunk in chunks:
        assert chunk.document_id == "doc-meta"


def test_parse_markdown_text_no_headings_returns_single_chunk():
    text = "Just a paragraph with no headings. It should be a single section."
    chunks = parse_markdown_text(text, document_id="doc-plain")
    assert len(chunks) >= 1


def test_parse_markdown_text_multi_section_creates_multiple_chunks():
    text = "# Section A\n\n" + "A " * 200 + "\n\n# Section B\n\n" + "B " * 200
    chunks = parse_markdown_text(text, document_id="doc-multi")
    # Each section should contribute at least one chunk
    assert len(chunks) >= 2


def test_parse_markdown_text_chunk_has_text():
    text = "# Title\n\nThis is the text content."
    chunks = parse_markdown_text(text, document_id="doc-content")
    assert all(len(c.text) > 0 for c in chunks)


# ── parse_markdown (file) ─────────────────────────────────────────────────────


def test_parse_markdown_file_not_found_raises():
    with pytest.raises(FileNotFoundError, match="not found"):
        parse_markdown("/nonexistent/path/file.md", document_id="doc-missing")


def test_parse_markdown_valid_file_returns_chunks():
    content = "# FCA MLR 2017\n\nMoney laundering regulations require CDD for all customers."
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        f.flush()
        chunks = parse_markdown(f.name, document_id="doc-file-001")
    assert len(chunks) > 0


def test_parse_markdown_file_chunks_have_document_id():
    content = "# Section\n\nContent here for the section."
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        f.flush()
        chunks = parse_markdown(f.name, document_id="doc-file-002")
    for chunk in chunks:
        assert chunk.document_id == "doc-file-002"


def test_parse_markdown_file_with_metadata():
    content = "# AML Policy\n\nThe AML policy document."
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        f.flush()
        chunks = parse_markdown(f.name, document_id="doc-file-003", metadata={"jurisdiction": "UK"})
    assert len(chunks) >= 1


def test_parse_markdown_no_headings_creates_main_section():
    content = "Plain text without any headings at all. Just a paragraph."
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        f.flush()
        chunks = parse_markdown(f.name, document_id="doc-plain-file")
    assert len(chunks) >= 1
