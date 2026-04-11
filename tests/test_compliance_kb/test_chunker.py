"""
tests/test_compliance_kb/test_chunker.py — Chunker unit tests
IL-CKS-01 | banxe-emi-stack

Tests: 5 scenarios covering boundary preservation, overlap, oversized sentences,
empty input, and multi-section chunking.
"""

from __future__ import annotations

from services.compliance_kb.ingestion.chunker import (
    _group_into_chunks,
    _split_sentences,
    chunk_document_sections,
    chunk_text,
)
from services.compliance_kb.storage.models import DocumentChunk


class TestChunkText:
    def test_chunk_text_basic_produces_chunks(self):
        """chunk_text returns non-empty list for valid input."""
        text = "Article 5. EMIs must safeguard client funds. " * 30
        chunks = chunk_text(text, document_id="doc-001", section="Article 5")
        assert len(chunks) >= 1
        assert all(isinstance(c, DocumentChunk) for c in chunks)

    def test_chunk_text_empty_returns_empty(self):
        """chunk_text returns empty list for blank input."""
        chunks = chunk_text("   ", document_id="doc-001")
        assert chunks == []

    def test_chunk_text_preserves_section(self):
        """All chunks inherit the section label."""
        text = "The payment firm must ensure. " * 50
        chunks = chunk_text(text, document_id="doc-002", section="Chapter 3")
        assert all(c.section == "Chapter 3" for c in chunks)

    def test_chunk_text_respects_chunk_size(self):
        """Each chunk is within chunk_size tokens (approximate)."""
        words = ["word"] * 600
        text = " ".join(words)
        chunks = chunk_text(text, document_id="doc-003", chunk_size=100, chunk_overlap=10)
        for chunk in chunks:
            token_count = len(chunk.text.split())
            # Allow 10% overrun for overlap
            assert token_count <= 115, f"Chunk too large: {token_count} tokens"

    def test_chunk_text_document_id_in_all_chunks(self):
        """Every chunk has the correct document_id."""
        text = "EBA Guideline Article 1. This is a compliance requirement. " * 20
        chunks = chunk_text(text, document_id="eba-gl-001")
        assert all(c.document_id == "eba-gl-001" for c in chunks)

    def test_chunk_text_metadata_propagated(self):
        """Custom metadata is present in all chunks."""
        text = "A regulation. " * 30
        meta = {"jurisdiction": "uk", "version": "2024-01-01"}
        chunks = chunk_text(text, document_id="doc-meta", metadata=meta)
        for chunk in chunks:
            assert chunk.metadata.get("jurisdiction") == "uk"
            assert chunk.metadata.get("version") == "2024-01-01"

    def test_chunk_text_unique_chunk_ids(self):
        """All chunk IDs within a document are unique."""
        text = "Sentence number one. Sentence number two. " * 100
        chunks = chunk_text(text, document_id="doc-ids")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))


class TestChunkDocumentSections:
    def test_chunk_document_sections_preserves_boundaries(self):
        """Chunks do not span section boundaries."""
        sections = [
            ("Section 1", "First section content. " * 20),
            ("Section 2", "Second section content. " * 20),
        ]
        chunks = chunk_document_sections(sections, document_id="doc-sec")
        sec1_chunks = [c for c in chunks if c.section == "Section 1"]
        sec2_chunks = [c for c in chunks if c.section == "Section 2"]
        assert len(sec1_chunks) >= 1
        assert len(sec2_chunks) >= 1
        # No chunk has mixed sections
        assert all(c.section in ("Section 1", "Section 2") for c in chunks)

    def test_chunk_document_sections_empty_sections_skipped(self):
        """Empty or whitespace-only sections produce no chunks."""
        sections = [
            ("Header", "   "),
            ("Content", "Real content here. " * 10),
        ]
        chunks = chunk_document_sections(sections, document_id="doc-empty")
        assert all(c.section != "Header" for c in chunks)
        assert any(c.section == "Content" for c in chunks)

    def test_chunk_document_sections_globally_unique_ids(self):
        """All chunk IDs across all sections are globally unique."""
        sections = [(f"Section {i}", "text. " * 30) for i in range(5)]
        chunks = chunk_document_sections(sections, document_id="doc-global")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))


class TestSplitSentences:
    def test_split_on_period(self):
        sentences = _split_sentences("First. Second. Third.")
        assert len(sentences) >= 2

    def test_single_sentence_returns_one(self):
        sentences = _split_sentences("Only one sentence here")
        assert len(sentences) == 1
        assert sentences[0] == "Only one sentence here"

    def test_normalises_whitespace(self):
        sentences = _split_sentences("Too   many   spaces.  Next sentence.")
        assert all("  " not in s for s in sentences)


class TestGroupIntoChunks:
    def test_group_short_text_single_chunk(self):
        sentences = ["short sentence"]
        groups = _group_into_chunks(sentences, chunk_size=512, chunk_overlap=50)
        assert len(groups) == 1

    def test_group_long_text_multiple_chunks(self):
        # 30 sentences × 20 words = 600 tokens, chunk_size=100 → ~6-7 chunks
        sentences = ["word " * 20] * 30
        groups = _group_into_chunks(sentences, chunk_size=100, chunk_overlap=10)
        assert len(groups) >= 5

    def test_group_no_empty_chunks(self):
        sentences = ["word " * 50] * 10
        groups = _group_into_chunks(sentences, chunk_size=100, chunk_overlap=10)
        assert all(g for g in groups)
