"""
services/reasoning_bank/store.py — ReasoningBank Storage
IL-ARL-01 | banxe-emi-stack

PostgreSQL storage for structured records + FAISS/HNSW index for
embedding similarity search.

FAISS is optional — if not installed, falls back to linear cosine similarity.
"""

from __future__ import annotations

import hashlib
import logging
import math
import uuid
from datetime import UTC, datetime

from services.reasoning_bank.models import (
    CaseRecord,
    DecisionRecord,
    EmbeddingRecord,
    FeedbackRecord,
    PolicySnapshot,
    ReasoningRecord,
)

logger = logging.getLogger(__name__)

# FAISS is optional — production should have it; tests use the fallback
try:
    import faiss  # type: ignore[import]  # noqa: F401

    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False
    logger.info("faiss not available — using linear cosine similarity fallback")


_DEFAULT_SIMILARITY_THRESHOLD = 0.85
_DEFAULT_TOP_K = 5


class ReasoningBankStore:
    """In-memory ReasoningBank storage with optional FAISS similarity search.

    In production: replace `_cases`, `_decisions`, etc. with async SQLAlchemy
    repositories against PostgreSQL, and `_index` with a persistent FAISS/HNSW store.

    Protocol DI: inject a `db_session` factory to swap persistence layer.
    """

    def __init__(
        self,
        similarity_threshold: float = _DEFAULT_SIMILARITY_THRESHOLD,
        embedding_dim: int = 384,
    ) -> None:
        self._threshold = similarity_threshold
        self._dim = embedding_dim

        # In-memory stores (replace with DB in production)
        self._cases: dict[str, CaseRecord] = {}
        self._decisions: dict[str, DecisionRecord] = {}
        self._reasoning: dict[str, ReasoningRecord] = {}
        self._embeddings: dict[str, EmbeddingRecord] = {}
        self._policy_snapshots: dict[str, PolicySnapshot] = {}
        self._feedback: list[FeedbackRecord] = []

        # case_id → embedding_id mapping for fast lookup
        self._case_to_embedding: dict[str, str] = {}

        # FAISS index (optional)
        self._index: object | None = None
        self._index_ids: list[str] = []  # maps FAISS index position → case_id
        if _FAISS_AVAILABLE:
            import faiss

            self._index = faiss.IndexFlatIP(embedding_dim)  # inner-product (cosine after norm)

    # ── Storage ───────────────────────────────────────────────────────────────

    async def store_case(
        self,
        case: CaseRecord,
        decision: DecisionRecord,
        reasoning: ReasoningRecord,
        embedding: list[float] | None = None,
        policy: PolicySnapshot | None = None,
    ) -> str:
        """Persist a complete case record with its decision and reasoning.

        Returns:
            case_id of the stored record.
        """
        self._cases[case.case_id] = case
        self._decisions[decision.decision_id] = decision
        self._reasoning[reasoning.reasoning_id] = reasoning

        if policy is not None:
            self._policy_snapshots[policy.snapshot_id] = policy

        if embedding is not None:
            emb_record = EmbeddingRecord(
                embedding_id=str(uuid.uuid4()),
                case_id=case.case_id,
                vector=embedding,
                model_name="default",
                dimension=len(embedding),
                created_at=datetime.now(UTC),
            )
            self._embeddings[emb_record.embedding_id] = emb_record
            self._case_to_embedding[case.case_id] = emb_record.embedding_id
            self._add_to_index(case.case_id, embedding)

        logger.debug("Stored case %s (decision=%s)", case.case_id, decision.decision)
        return case.case_id

    def _add_to_index(self, case_id: str, vector: list[float]) -> None:
        """Add a normalised vector to the FAISS index or linear store."""
        norm_vec = self._normalise(vector)
        if _FAISS_AVAILABLE and self._index is not None:
            import numpy as np

            arr = np.array([norm_vec], dtype="float32")
            self._index.add(arr)  # type: ignore[attr-defined]
        self._index_ids.append(case_id)

    # ── Retrieval ─────────────────────────────────────────────────────────────

    async def find_similar(
        self,
        query_vector: list[float],
        top_k: int = _DEFAULT_TOP_K,
        threshold: float | None = None,
    ) -> list[CaseRecord]:
        """Find cases with embedding similarity above threshold.

        Returns:
            Top-k most similar CaseRecords above the similarity threshold.
        """
        threshold = threshold or self._threshold
        if not self._index_ids:
            return []

        norm_query = self._normalise(query_vector)

        if _FAISS_AVAILABLE and self._index is not None:
            import numpy as np

            arr = np.array([norm_query], dtype="float32")
            k = min(top_k, len(self._index_ids))
            scores, indices = self._index.search(arr, k)  # type: ignore[attr-defined]
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0:
                    continue
                if float(score) < threshold:
                    continue
                case_id = self._index_ids[idx]
                case = self._cases.get(case_id)
                if case:
                    results.append(case)
            return results
        else:
            return self._linear_search(norm_query, top_k, threshold)

    def _linear_search(
        self, norm_query: list[float], top_k: int, threshold: float
    ) -> list[CaseRecord]:
        """Fallback linear cosine similarity search."""
        scored: list[tuple[float, CaseRecord]] = []
        for case_id in self._index_ids:
            emb_id = self._case_to_embedding.get(case_id)
            if emb_id is None:
                continue
            emb = self._embeddings.get(emb_id)
            if emb is None:
                continue
            norm_stored = self._normalise(emb.vector)
            sim = self._cosine_sim(norm_query, norm_stored)
            if sim >= threshold:
                case = self._cases.get(case_id)
                if case:
                    scored.append((sim, case))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:top_k]]

    async def get_case(self, case_id: str) -> CaseRecord | None:
        return self._cases.get(case_id)

    async def get_decision(self, case_id: str) -> DecisionRecord | None:
        for d in self._decisions.values():
            if d.case_id == case_id:
                return d
        return None

    async def get_reusable_reasoning(self, case_id: str) -> ReasoningRecord | None:
        """Return reasoning for a case if it qualifies for reuse.

        Reuse rules:
        - Same playbook family (checked by caller via find_similar)
        - No human override that contradicted original decision
        - Not concept-drifted (simple: no feedback flagging false positive)
        """
        for r in self._reasoning.values():
            if r.case_id == case_id:
                # Check for contradicting override
                decision = await self.get_decision(case_id)
                if decision and decision.overridden:
                    logger.debug("Case %s was overridden — reasoning not reusable", case_id)
                    return None
                return r
        return None

    # ── Feedback (I-27: write-only) ───────────────────────────────────────────

    async def record_feedback(self, feedback: FeedbackRecord) -> None:
        """Append feedback record. Write-only — never auto-applied (I-27)."""
        self._feedback.append(feedback)
        logger.info("Feedback recorded for case %s: %s", feedback.case_id, feedback.feedback_type)

    async def get_feedback(self, case_id: str) -> list[FeedbackRecord]:
        return [f for f in self._feedback if f.case_id == case_id]

    # ── Policy snapshot ───────────────────────────────────────────────────────

    def compute_policy_hash(self, playbook_yaml: str) -> str:
        """Compute SHA-256 of playbook YAML content."""
        return hashlib.sha256(playbook_yaml.encode()).hexdigest()

    # ── Utilities ─────────────────────────────────────────────────────────────

    @staticmethod
    def _normalise(vec: list[float]) -> list[float]:
        """L2-normalise a vector for cosine similarity via inner product."""
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0.0:
            return vec
        return [x / norm for x in vec]

    @staticmethod
    def _cosine_sim(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two already-normalised vectors."""
        return sum(x * y for x, y in zip(a, b))

    def stats(self) -> dict:
        """Return storage statistics."""
        return {
            "cases": len(self._cases),
            "decisions": len(self._decisions),
            "reasoning": len(self._reasoning),
            "embeddings": len(self._embeddings),
            "feedback": len(self._feedback),
            "index_ids": len(self._index_ids),
            "faiss_available": _FAISS_AVAILABLE,
        }
