"""
services/crypto_aml_graph/neo4j_adapter.py — Graph store adapters
GAP-068 | IMPL-2 | banxe-emi-stack

GraphStorePort implementations: an in-memory store (default, test-safe) and a
lazy Neo4j adapter that connects only when NEO4J_URI is configured (no secrets in
code; the driver is imported lazily so the dependency is optional).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class InMemoryGraphStore:
    """Default GraphStorePort — an explicit adjacency map (safe, no I/O)."""

    def __init__(self, edges: dict[str, list[str]] | None = None) -> None:
        self._edges: dict[str, list[str]] = edges or {}

    def neighbors(self, address: str) -> list[str]:
        return list(self._edges.get(address, []))

    def tx_count(self, address: str) -> int:
        return len(self._edges.get(address, []))


class Neo4jGraphAdapter:
    """Lazy Neo4j GraphStorePort. Connects only when NEO4J_URI is set."""

    def __init__(self, uri: str | None = None) -> None:
        self._uri = uri or os.environ.get("NEO4J_URI", "")
        self._user = os.environ.get("NEO4J_USER", "neo4j")
        self._password = os.environ.get("NEO4J_PASSWORD", "")
        self._driver = None

    def _connect(self) -> None:
        if self._driver is not None or not self._uri:
            return
        from neo4j import GraphDatabase  # lazy — optional dependency

        self._driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))

    def neighbors(self, address: str) -> list[str]:
        self._connect()
        if self._driver is None:
            logger.info("Neo4j not configured — no neighbours for %s", address)
            return []
        query = (
            "MATCH (a:Address {hash: $addr})-[:SENT|RECEIVED]-(b:Address) "
            "RETURN b.hash AS hash LIMIT 100"
        )
        with self._driver.session() as session:
            return [record["hash"] for record in session.run(query, addr=address)]

    def tx_count(self, address: str) -> int:
        return len(self.neighbors(address))
