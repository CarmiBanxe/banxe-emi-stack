"""
services/crypto_aml_graph/gnn_inference.py — GraphSAGE laundering-risk inference
GAP-068 | IMPL-2 | banxe-emi-stack

GraphSAGE inference seam. When no trained model is available (default), a
deterministic rule-based peel-chain / Random-Forest-style fallback produces the
laundering-risk score from graph features — so the service is fully functional
without the ML artifact, and upgrades transparently when a model is wired in.
"""

from __future__ import annotations

from decimal import Decimal
import logging

from services.crypto_aml_graph.models import GnnFeatures

logger = logging.getLogger(__name__)


class GraphSageInference:
    """Laundering-risk scorer. Uses a loaded model if present, else a rule fallback."""

    def __init__(self, model: object | None = None) -> None:
        self._model = model

    def score(self, features: GnnFeatures) -> Decimal:
        if self._model is not None:
            return self._score_model(features)
        return self._score_fallback(features)

    def _score_model(self, features: GnnFeatures) -> Decimal:
        # Seam for a real GraphSAGE artifact. Until wired, fall back deterministically.
        logger.info("GraphSAGE model present but inference not wired — using fallback")
        return self._score_fallback(features)

    @staticmethod
    def _score_fallback(features: GnnFeatures) -> Decimal:
        """Rule-based peel-chain / consolidation heuristic (0-100)."""
        score = Decimal("0")
        # Large CIOH cluster → consolidation / mule network.
        score += min(Decimal("40"), Decimal(features.cluster_size) * Decimal("2"))
        # High fan-in/out neighbour count → layering.
        score += min(Decimal("20"), Decimal(features.neighbor_count) * Decimal("1"))
        # Deep peel chains → classic laundering structure.
        score += min(Decimal("20"), Decimal(features.peel_chain_depth) * Decimal("4"))
        # Direct proximity to known-bad addresses dominates.
        score += min(Decimal("60"), Decimal(features.blacklist_proximity) * Decimal("30"))
        return min(Decimal("100"), score)
