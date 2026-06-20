"""
services/crypto_aml_graph/clustering.py — CIOH entity clustering
GAP-068 | IMPL-2 | banxe-emi-stack

Common-Input-Ownership Heuristic (CIOH): for a UTXO-chain (BTC) transaction, all
input addresses are assumed to belong to the same controlling entity. Used to
size the entity behind an incoming transfer (a large consolidation cluster is a
laundering-risk signal).
"""

from __future__ import annotations

from decimal import Decimal


class CIOHClusterer:
    """Cluster co-spent input addresses into a single controlling entity."""

    def cluster(self, tx_inputs: list[str], seed: str | None = None) -> frozenset[str]:
        """Return the CIOH cluster for a transaction's inputs (+ optional seed address)."""
        members = {addr for addr in tx_inputs if addr}
        if seed:
            members.add(seed)
        return frozenset(members)

    def cluster_risk_score(self, cluster_size: int) -> Decimal:
        """Map cluster size to a 0-100 consolidation-risk signal (saturating)."""
        if cluster_size <= 1:
            return Decimal("0")
        return min(Decimal("100"), Decimal(cluster_size) * Decimal("5"))
