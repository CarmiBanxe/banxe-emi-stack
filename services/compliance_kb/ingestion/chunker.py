"""
services/compliance_kb/ingestion/chunker.py — Semantic chunker
IL-CKS-01 | banxe-emi-stack

Splits documents into overlapping chunks that preserve section boundaries.
Chunk size: 512 tokens | Overlap: 50 tokens | Whitespace tokenisation.
"""

from __future__ import annotations

import re
from typing import Any

from services.compliance_kb.constants import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE
from services.compliance_kb.storage.chroma_store import make_chunk_id
from services.compliance_kb.storage.models import DocumentChunk

# ── Public API ─────────────────────────────────────────────────────────────


def chunk_text(
    text: str,
    document_id: str,
    section: str = "main",
    page: int | None = None,
    metadata: dict[str, Any] | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """Split *text* into overlapping chunks, returning DocumentChunk objects.

    Strategy:
    1. Split on sentence boundaries when possible.
    2. Respect chunk_size (in whitespace-split tokens, not BPE).
    3. Add overlap by carrying the tail of the previous chunk.
    4. Never produce empty chunks.

    Args:
        text: Raw text to chunk.
        document_id: ID of the parent ComplianceDocument.
        section: Section label (e.g. "Article 5", "Chapter 3").
        page: Source page number (optional).
        metadata: Extra metadata propagated to each chunk.
        chunk_size: Maximum tokens per chunk.
        chunk_overlap: Number of overlap tokens between consecutive chunks.

    Returns:
        List of DocumentChunk objects.
    """
    if not text or not text.strip():
        return []

    meta = dict(metadata or {})
    sentences = _split_sentences(text)
    token_groups = _group_into_chunks(sentences, chunk_size, chunk_overlap)

    chunks: list[DocumentChunk] = []
    char_cursor = 0
    for idx, token_group in enumerate(token_groups):
        chunk_text_str = " ".join(token_group)
        if not chunk_text_str.strip():
            continue

        char_start = text.find(chunk_text_str[:30], char_cursor)
        if char_start == -1:
            char_start = char_cursor
        char_end = char_start + len(chunk_text_str)
        char_cursor = max(char_cursor, char_end - len(" ".join(token_group[-chunk_overlap:])))

        chunks.append(
            DocumentChunk(
                chunk_id=make_chunk_id(document_id, idx),
                document_id=document_id,
                section=section,
                text=chunk_text_str,
                page=page,
                char_start=char_start,
                char_end=char_end,
                metadata=meta,
            )
        )
    return chunks


def chunk_document_sections(
    sections: list[tuple[str, str]],
    document_id: str,
    page_map: dict[str, int] | None = None,
    metadata: dict[str, Any] | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """Chunk a document that is already split into (section_name, text) pairs.

    Preserves section boundaries — chunks do not span section borders.

    Args:
        sections: List of (section_name, section_text) tuples.
        document_id: Parent document ID.
        page_map: Optional mapping from section_name → page number.
        metadata: Extra metadata propagated to all chunks.
        chunk_size: Maximum tokens per chunk.
        chunk_overlap: Overlap tokens between chunks within a section.

    Returns:
        Flat list of DocumentChunk objects, ordered by section then position.
    """
    all_chunks: list[DocumentChunk] = []
    global_idx = 0

    for section_name, section_text in sections:
        page = (page_map or {}).get(section_name)
        section_chunks = chunk_text(
            text=section_text,
            document_id=document_id,
            section=section_name,
            page=page,
            metadata=metadata,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        # Re-index to ensure globally unique chunk IDs
        for chunk in section_chunks:
            chunk.chunk_id = make_chunk_id(document_id, global_idx)
            global_idx += 1
        all_chunks.extend(section_chunks)

    return all_chunks


# ── Internal helpers ───────────────────────────────────────────────────────

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using simple punctuation heuristics."""
    cleaned = " ".join(text.split())  # normalise whitespace
    parts = _SENTENCE_END.split(cleaned)
    return [p.strip() for p in parts if p.strip()]


def _tokenize(text: str) -> list[str]:
    """Whitespace tokenisation — fast, language-agnostic."""
    return text.split()


def _group_into_chunks(
    sentences: list[str],
    chunk_size: int,
    chunk_overlap: int,
) -> list[list[str]]:
    """Group tokenised sentences into overlapping token chunks.

    Returns a list of token lists (each list is one chunk).
    """
    chunks: list[list[str]] = []
    current_tokens: list[str] = []

    for sentence in sentences:
        sent_tokens = _tokenize(sentence)

        # If a single sentence exceeds chunk_size, hard-split it
        if len(sent_tokens) > chunk_size:
            # Flush current buffer first
            if current_tokens:
                chunks.append(list(current_tokens))
                current_tokens = current_tokens[-chunk_overlap:] if chunk_overlap else []

            # Hard-split the oversized sentence
            for i in range(0, len(sent_tokens), chunk_size - chunk_overlap):
                sub = sent_tokens[i : i + chunk_size]
                if sub:
                    chunks.append(sub)
            # Carry overlap from last sub-chunk
            last_sub = sent_tokens[-(chunk_size - chunk_overlap) :] if chunk_overlap else []
            current_tokens = list(last_sub)
            continue

        if len(current_tokens) + len(sent_tokens) > chunk_size:
            if current_tokens:
                chunks.append(list(current_tokens))
            # Start new chunk with overlap from previous
            overlap_start = max(0, len(current_tokens) - chunk_overlap)
            current_tokens = current_tokens[overlap_start:] + sent_tokens
        else:
            current_tokens.extend(sent_tokens)

    if current_tokens:
        chunks.append(list(current_tokens))

    return [c for c in chunks if c]
