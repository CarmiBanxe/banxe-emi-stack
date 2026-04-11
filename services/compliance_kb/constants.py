"""
services/compliance_kb/constants.py — KB constants and tag taxonomy
IL-CKS-01 | banxe-emi-stack
"""

from __future__ import annotations

# ── Embedding ──────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# ── Chunking ───────────────────────────────────────────────────────────────
DEFAULT_CHUNK_SIZE = 512  # tokens
DEFAULT_CHUNK_OVERLAP = 50  # tokens

# ── Search ─────────────────────────────────────────────────────────────────
DEFAULT_MAX_RESULTS = 10
SIMILARITY_THRESHOLD = 0.7

# ── Collection names (one per compliance notebook) ─────────────────────────
COLLECTION_EU_AML = "emi-eu-aml"
COLLECTION_UK_FCA = "emi-uk-fca"
COLLECTION_INTERNAL_SOP = "emi-internal-sop"
COLLECTION_CASE_HISTORY = "emi-case-history"

ALL_COLLECTIONS = [
    COLLECTION_EU_AML,
    COLLECTION_UK_FCA,
    COLLECTION_INTERNAL_SOP,
    COLLECTION_CASE_HISTORY,
]

# ── Tag taxonomy ───────────────────────────────────────────────────────────
VALID_TAGS: frozenset[str] = frozenset(
    [
        "emi",
        "aml",
        "kyc",
        "regulator",
        "fca",
        "uk",
        "eu",
        "fatf",
        "eba",
        "esma",
        "internal",
        "sop",
        "sar",
        "str",
        "history",
        "pep",
        "sanctions",
        "cass",
        "psd2",
        "mlr",
        "psr",
        "ctf",
    ]
)

# ── RAG prompt template ────────────────────────────────────────────────────
RAG_SYSTEM_PROMPT = (
    "You are a compliance officer assistant for Banxe EMI, an FCA-authorised "
    "Electronic Money Institution. Answer the question using ONLY the provided "
    "regulatory context. Cite the source document and section for each claim. "
    "If the context does not contain enough information, say so explicitly."
)
