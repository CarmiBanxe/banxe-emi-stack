"""
services/adverse_media/rss_feed.py — RSS/Atom adverse-media source adapter.

GAP-064 sibling of feed.py::OpenSanctionsAdjacencyFeed and x_feed.py::XAdverseMediaFeed.
Implements the NegativeNewsFeed Protocol so curated negative-news RSS/Atom feeds
(e.g. regulator press releases, court-reporting outlets) can supply candidate
articles to the SAME governed adverse-media screening path — MLR 2017 Reg.28(3),
FCA SYSC 6.3, Banxe I-04.

REGULATORY POSTURE (unchanged from the service): advisory ONLY. This feed only
SUPPLIES candidate articles; it makes NO decision. AdverseMediaService routes any
hit to MANDATORY MLRO HITL review (no auto-clear, no auto-block). Real entity
matching happens downstream in matcher.py — this adapter applies only a coarse
relevance pre-filter and never decides anything.

⚠️ SANDBOX / NON-PROD:
    Disabled by default. With no explicit opt-in it returns [] (safe stub, no
    network, no secrets) — identical degrade-to-[] contract as the sibling feeds.
    In SANDBOX this feed DOES NOT participate in screening or any customer decision.
    PROD ENABLEMENT REQUIRES, separately, all of:
      - compliance/MLRO sign-off of each RSS source as an approved adverse-media
        source,
      - a data-protection / lawful-basis assessment (UK GDPR) for the source set,
      - ADVERSE_MEDIA_RSS_ENABLED=1 AND ADVERSE_MEDIA_RSS_URLS in env
        (comma-separated, env only — never in code),
      - ADR ratification of the adverse-media multi-node feed framework.
    Until then this adapter is inert.

SECURITY: fetched XML is validated with defusedxml BEFORE parsing (DTDs, entity
definitions and external references are all rejected — XXE-safe); a feed that is
not well-formed, entity-free XML is dropped. Any fetch/parse error degrades to []
and never breaks screening. Subject names are NOT logged (R-SEC / PII).
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as _defused_fromstring
import feedparser
import httpx

from services.adverse_media.models import AdverseMediaArticle

logger = logging.getLogger(__name__)

_HEADLINE_MAX = 120


class RssAdverseMediaFeed:
    """Adverse-media candidate feed backed by configured RSS/Atom sources.

    SANDBOX-OFF by default: returns [] unless ADVERSE_MEDIA_RSS_ENABLED=1 AND
    ADVERSE_MEDIA_RSS_URLS is set. Any error degrades to [] — a feed failure
    never breaks screening. Implements the NegativeNewsFeed Protocol.
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        urls: list[str] | None = None,
        timeout_s: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        # explicit opt-in; default OFF (sandbox posture)
        env_on = os.environ.get("ADVERSE_MEDIA_RSS_ENABLED", "") == "1"
        self._enabled = env_on if enabled is None else enabled
        raw_urls = os.environ.get("ADVERSE_MEDIA_RSS_URLS", "") if urls is None else ",".join(urls)
        self._urls = [u.strip() for u in raw_urls.split(",") if u.strip()]
        self._timeout_s = timeout_s
        self._transport = transport

    def fetch(self, name: str, *, jurisdiction: str | None = None) -> list[AdverseMediaArticle]:
        # SANDBOX / not-enabled → inert, no network, no decision impact.
        if not self._enabled or not self._urls:
            logger.info("RSS adverse-media feed disabled (sandbox) — no hits")  # no name logged
            return []
        articles: list[AdverseMediaArticle] = []
        for url in self._urls:
            # one bad source never breaks the others
            articles.extend(self._fetch_one(url, name, jurisdiction))
        return articles

    def _fetch_one(
        self, url: str, name: str, jurisdiction: str | None
    ) -> list[AdverseMediaArticle]:
        domain = urlparse(url).netloc or "unknown"
        try:
            with httpx.Client(timeout=self._timeout_s, transport=self._transport) as client:
                resp = client.get(url)
                resp.raise_for_status()
                raw = resp.content
        except httpx.HTTPError as exc:
            logger.error("RSS adverse-media fetch error (%s): %s", domain, exc)  # no PII in log
            return []
        if not _xml_is_safe(raw):
            logger.warning("RSS adverse-media source rejected — unsafe/malformed XML (%s)", domain)
            return []
        parsed = feedparser.parse(raw)
        results: list[AdverseMediaArticle] = []
        for entry in parsed.get("entries", []):
            if not _relevant(entry, name):
                continue
            results.append(
                _to_article(entry, domain=domain, subject=name, jurisdiction=jurisdiction)
            )
        return results


def _xml_is_safe(raw: bytes) -> bool:
    """Reject XML containing DTDs, entity definitions or external references (XXE).

    defusedxml raises on forbidden constructs; anything that is not well-formed,
    entity-free XML is treated as unsafe (conservative sandbox posture).
    """
    try:
        _defused_fromstring(raw.decode("utf-8", errors="replace"), forbid_dtd=True)
    except (DefusedXmlException, SyntaxError, ValueError):
        return False
    return True


def _relevant(entry: dict, name: str) -> bool:
    """Coarse pre-filter only — real fuzzy matching lives in matcher.py."""
    haystack = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
    return name.lower() in haystack


def _to_article(
    entry: dict, *, domain: str, subject: str, jurisdiction: str | None
) -> AdverseMediaArticle:
    entry_id = str(entry.get("id") or entry.get("link") or entry.get("title", ""))
    title = str(entry.get("title", ""))
    return AdverseMediaArticle(
        article_id=f"rss:{domain}:{entry_id}",
        subject_name=subject,
        headline=title[:_HEADLINE_MAX],
        source=f"rss:{domain}",
        categories=["rss-osint"],
        subject_dob=None,
        subject_jurisdiction=jurisdiction,
        url=entry.get("link"),
        published=entry.get("published") or entry.get("updated"),
        snippet=entry.get("summary"),
    )
