"""
services/crypto_aml_graph/graphsense_client.py — GraphSense API client
GAP-068 | IMPL-2 | banxe-emi-stack

Pluggable GraphSense client. Holds NO secrets and performs NO network call when
unconfigured — a safe-stub returning None / [] (ACCESS-AND-SECRETS I-SEC).
Configure GRAPHSENSE_URL (+ optional GRAPHSENSE_API_KEY via env only) to enable.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


class GraphSenseClient:
    """Read-only GraphSense entity/cluster lookups (safe-stub when unconfigured)."""

    def __init__(self, base_url: str | None = None, timeout_s: float = 5.0) -> None:
        self._base_url = (base_url or os.environ.get("GRAPHSENSE_URL", "")).rstrip("/")
        self._api_key = os.environ.get("GRAPHSENSE_API_KEY", "")
        self._timeout_s = timeout_s

    @property
    def configured(self) -> bool:
        return bool(self._base_url)

    def fetch_entity(self, address: str, chain: str) -> dict | None:
        """Return GraphSense entity/cluster JSON for an address, or None (safe-stub)."""
        if not self._base_url:
            logger.info("GraphSense not configured — safe-stub (None) for %s/%s", chain, address)
            return None
        headers = {"Authorization": self._api_key} if self._api_key else {}
        url = f"{self._base_url}/{chain.lower()}/addresses/{address}/entity"
        try:
            with httpx.Client(timeout=self._timeout_s) as client:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("GraphSense error for %s/%s: %s", chain, address, exc)
            return None
        return data if isinstance(data, dict) else None

    def neighbor_addresses(self, address: str, chain: str) -> list[str]:
        """Best-effort neighbour addresses from GraphSense (empty when unconfigured)."""
        entity = self.fetch_entity(address, chain)
        if not entity:
            return []
        neighbors = entity.get("neighbors", [])
        return [str(n.get("address", "")) for n in neighbors if n.get("address")]
