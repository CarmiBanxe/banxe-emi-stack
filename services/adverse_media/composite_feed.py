"""
services/adverse_media/composite_feed.py — multi-node feed aggregator.

GAP-064. Implements the NegativeNewsFeed Protocol by fanning a single fetch()
out to a list of sub-feeds (OpenSanctionsAdjacencyFeed, XAdverseMediaFeed,
RssAdverseMediaFeed, WebSearchAdverseMediaFeed, …), concatenating and
de-duplicating the results. AdverseMediaService takes exactly ONE feed —
CompositeFeed is that single injected feed; the service itself is unchanged.

REGULATORY POSTURE (unchanged): advisory ONLY. Aggregation adds NO decision
logic — every candidate article still flows through AdverseMediaService's
matcher and, on a hit, MANDATORY MLRO HITL review (no auto-clear, no auto-block).

⚠️ SANDBOX / NON-PROD:
    The aggregator itself holds no configuration and no secrets. Each sub-feed
    keeps its own SANDBOX-off env gating — composing feeds that are all disabled
    yields [] exactly like a safe stub. PROD enablement is decided per sub-feed
    (compliance/MLRO sign-off + UK GDPR lawful-basis + ADR ratification), never
    by this aggregator.

RESILIENCE: each sub-feed is isolated — one sub-feed raising or returning []
never breaks the others (degrade-to-[] per node). No subject-name/PII in logs.
"""

from __future__ import annotations

import logging

from services.adverse_media.models import AdverseMediaArticle, NegativeNewsFeed

logger = logging.getLogger(__name__)


class CompositeFeed:
    """Aggregates multiple NegativeNewsFeed nodes behind a single fetch().

    De-duplicates by article_id, with (source, url) as a fallback key. Sub-feed
    failures are isolated to that sub-feed (degrade-to-[]). Implements the
    NegativeNewsFeed Protocol.
    """

    def __init__(self, feeds: list[NegativeNewsFeed]) -> None:
        self._feeds = list(feeds)

    def fetch(self, name: str, *, jurisdiction: str | None = None) -> list[AdverseMediaArticle]:
        combined: list[AdverseMediaArticle] = []
        seen_ids: set[str] = set()
        seen_source_url: set[tuple[str, str]] = set()
        for feed in self._feeds:
            try:
                articles = feed.fetch(name, jurisdiction=jurisdiction)
            except Exception as exc:  # isolate the failing node — never break screening
                logger.error(
                    "composite adverse-media sub-feed %s failed: %s",
                    type(feed).__name__,
                    exc,
                )  # no name/PII in log
                articles = []
            for article in articles:
                if article.article_id and article.article_id in seen_ids:
                    continue
                source_url = (article.source, article.url or "")
                if article.url and source_url in seen_source_url:
                    continue
                if article.article_id:
                    seen_ids.add(article.article_id)
                if article.url:
                    seen_source_url.add(source_url)
                combined.append(article)
        return combined
