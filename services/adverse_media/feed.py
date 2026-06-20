"""
services/adverse_media/feed.py — Adverse-media source adapters
GAP-064 | IMPL-1 | banxe-emi-stack

Pluggable negative-news feeds. The default OpenSanctions-adjacency feed performs
NO network call and holds NO secrets when unconfigured (safe-stub returning []).
Configure ADVERSE_MEDIA_FEED_URL (+ optional ADVERSE_MEDIA_FEED_TOKEN, via env only —
never in code, ACCESS-AND-SECRETS I-SEC) to enable a live feed.
"""

from __future__ import annotations

import logging
import os

import httpx

from services.adverse_media.models import AdverseMediaArticle

logger = logging.getLogger(__name__)


class OpenSanctionsAdjacencyFeed:
    """Default adverse-media feed.

    Queries an OpenSanctions-compatible adverse-media endpoint when
    ADVERSE_MEDIA_FEED_URL is set; otherwise returns [] (safe stub, no network,
    no secrets). A feed error never breaks screening — it degrades to [].
    """

    def __init__(self, feed_url: str | None = None, timeout_s: float = 5.0) -> None:
        self._feed_url = (feed_url or os.environ.get("ADVERSE_MEDIA_FEED_URL", "")).rstrip("/")
        self._token = os.environ.get("ADVERSE_MEDIA_FEED_TOKEN", "")
        self._timeout_s = timeout_s

    def fetch(self, name: str, *, jurisdiction: str | None = None) -> list[AdverseMediaArticle]:
        if not self._feed_url:
            logger.info("adverse-media feed not configured — safe-stub (no hits) for %s", name)
            return []
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        params: dict[str, str] = {"q": name}
        if jurisdiction:
            params["jurisdiction"] = jurisdiction
        try:
            with httpx.Client(timeout=self._timeout_s) as client:
                resp = client.get(f"{self._feed_url}/search", params=params, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("adverse-media feed error for %s: %s", name, exc)
            return []
        results = payload.get("results", []) if isinstance(payload, dict) else []
        return [_to_article(item) for item in results]


def _to_article(item: dict) -> AdverseMediaArticle:
    return AdverseMediaArticle(
        article_id=str(item.get("id", "")),
        subject_name=str(item.get("name", "")),
        headline=str(item.get("headline", item.get("title", ""))),
        source=str(item.get("source", "openSanctions")),
        categories=list(item.get("topics", item.get("categories", []))),
        subject_dob=item.get("dob"),
        subject_jurisdiction=item.get("jurisdiction"),
        url=item.get("url"),
        published=item.get("published"),
        snippet=item.get("snippet"),
    )
