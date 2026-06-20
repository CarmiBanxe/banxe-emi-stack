"""
services/crypto_aml_graph/blacklist_feed.py — Ensemble blacklist feed
GAP-068 | IMPL-2 | banxe-emi-stack

Combines multiple crypto blacklist sources (0xB10C OFAC crypto list, USDT
blacklist, pluggable Scorechain / MistTrack). Each remote adapter is configured
by env URL only (no secrets in code) and degrades to [] when unconfigured. A
static map may be injected for deterministic config/tests.
"""

from __future__ import annotations

import logging
import os

import httpx

from services.crypto_aml_graph.models import BlacklistFeedPort, BlacklistFlag, FlagCategory

logger = logging.getLogger(__name__)


class _RemoteListAdapter:
    """Generic env-configured blacklist source (safe-stub when URL unset)."""

    def __init__(self, source: str, env_url: str, category: FlagCategory, severity: int) -> None:
        self._source = source
        self._url = os.environ.get(env_url, "").rstrip("/")
        self._category = category
        self._severity = severity

    def check(self, address: str, chain: str) -> list[BlacklistFlag]:
        if not self._url:
            return []
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self._url}/check", params={"address": address, "chain": chain})
                resp.raise_for_status()
                hit = bool(resp.json().get("listed", False))
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("blacklist source %s error: %s", self._source, exc)
            return []
        if not hit:
            return []
        return [
            BlacklistFlag(
                source=self._source,
                category=self._category,
                severity=self._severity,
                detail=f"listed by {self._source}",
            )
        ]


class EnsembleBlacklistFeed(BlacklistFeedPort):
    """Union of a static (config/test) map and any configured remote adapters."""

    def __init__(
        self,
        static_blacklist: dict[str, list[BlacklistFlag]] | None = None,
        adapters: list[_RemoteListAdapter] | None = None,
    ) -> None:
        self._static = static_blacklist or {}
        self._adapters = adapters if adapters is not None else _default_adapters()

    def check(self, address: str, chain: str) -> list[BlacklistFlag]:
        flags: list[BlacklistFlag] = list(self._static.get(address, []))
        for adapter in self._adapters:
            flags.extend(adapter.check(address, chain))
        return flags


def _default_adapters() -> list[_RemoteListAdapter]:
    return [
        _RemoteListAdapter("ofac-0xB10C", "OFAC_CRYPTO_LIST_URL", FlagCategory.SANCTIONS, 100),
        _RemoteListAdapter("usdt-blacklist", "USDT_BLACKLIST_URL", FlagCategory.SANCTIONS, 100),
        _RemoteListAdapter("scorechain", "SCORECHAIN_URL", FlagCategory.MIXER, 70),
        _RemoteListAdapter("misttrack", "MISTTRACK_URL", FlagCategory.SCAM, 60),
    ]
