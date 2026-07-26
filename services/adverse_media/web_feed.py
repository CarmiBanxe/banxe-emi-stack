"""
services/adverse_media/web_feed.py — generic web-search adverse-media adapter.

GAP-064 sibling of feed.py::OpenSanctionsAdjacencyFeed and x_feed.py::XAdverseMediaFeed.
Implements the NegativeNewsFeed Protocol so a configured negative-news web-search
endpoint (any provider exposing a JSON search API — NO provider is hardcoded) can
supply candidate articles to the SAME governed adverse-media screening path —
MLR 2017 Reg.28(3), FCA SYSC 6.3, Banxe I-04.

REGULATORY POSTURE (unchanged from the service): advisory ONLY. This feed only
SUPPLIES candidate articles; it makes NO decision. AdverseMediaService routes any
hit to MANDATORY MLRO HITL review (no auto-clear, no auto-block). Web-search
results are UNVERIFIED open-source material — they can raise a review flag, never
decide onboarding or block a transaction on their own.

⚠️ SANDBOX / NON-PROD:
    Disabled by default. With no explicit opt-in it returns [] (safe stub, no
    network, no secrets) — identical degrade-to-[] contract as the sibling feeds.
    In SANDBOX this feed DOES NOT participate in screening or any customer decision.
    PROD ENABLEMENT REQUIRES, separately, all of:
      - compliance/MLRO sign-off of the chosen search provider as an approved
        adverse-media source,
      - a data-protection / lawful-basis assessment (UK GDPR) for screening
        individuals against open web content,
      - ADVERSE_MEDIA_WEB_ENABLED=1 AND ADVERSE_MEDIA_WEB_SEARCH_URL AND
        ADVERSE_MEDIA_WEB_SEARCH_TOKEN in env (env only — never in code),
      - ADR ratification of the adverse-media multi-node feed framework.
    Until then this adapter is inert.

SECRETS (I-SEC / ACCESS-AND-SECRETS): the search token is read from env only,
never logged, never held in code. Subject names are NOT logged (R-SEC / PII).
Any error degrades to [] and never breaks screening.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

import httpx

from services.adverse_media.models import AdverseMediaArticle

logger = logging.getLogger(__name__)

_HEADLINE_MAX = 120


class WebSearchAdverseMediaFeed:
    """Adverse-media candidate feed backed by a configured web-search endpoint.

    SANDBOX-OFF by default: returns [] unless ADVERSE_MEDIA_WEB_ENABLED=1 AND
    both ADVERSE_MEDIA_WEB_SEARCH_URL and ADVERSE_MEDIA_WEB_SEARCH_TOKEN are set.
    Any error degrades to [] — a feed failure never breaks screening.
    Implements the NegativeNewsFeed Protocol.
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        timeout_s: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        # explicit opt-in; default OFF (sandbox posture)
        env_on = os.environ.get("ADVERSE_MEDIA_WEB_ENABLED", "") == "1"
        self._enabled = env_on if enabled is None else enabled
        self._search_url = os.environ.get("ADVERSE_MEDIA_WEB_SEARCH_URL", "").rstrip("/")
        self._token = os.environ.get("ADVERSE_MEDIA_WEB_SEARCH_TOKEN", "")
        self._timeout_s = timeout_s
        self._transport = transport

    def fetch(self, name: str, *, jurisdiction: str | None = None) -> list[AdverseMediaArticle]:
        # SANDBOX / not-enabled → inert, no network, no decision impact.
        if not self._enabled or not self._search_url or not self._token:
            logger.info("web adverse-media feed disabled (sandbox) — no hits")  # no name logged
            return []
        params: dict[str, str] = {"q": name}
        if jurisdiction:
            params["jurisdiction"] = jurisdiction
        headers = {"Authorization": f"Bearer {self._token}"}
        search_host = urlparse(self._search_url).netloc or "unknown"
        try:
            with httpx.Client(timeout=self._timeout_s, transport=self._transport) as client:
                resp = client.get(self._search_url, params=params, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("web adverse-media feed error (%s): %s", search_host, exc)  # no PII
            return []
        results = payload.get("results", []) if isinstance(payload, dict) else []
        return [
            _to_article(item, search_host=search_host, subject=name, jurisdiction=jurisdiction)
            for item in results
            if isinstance(item, dict)
        ]


def _to_article(
    item: dict, *, search_host: str, subject: str, jurisdiction: str | None
) -> AdverseMediaArticle:
    url = item.get("url")
    host = urlparse(str(url)).netloc if url else ""
    title = str(item.get("title", item.get("headline", "")))
    return AdverseMediaArticle(
        article_id=f"web:{item.get('id') or url or title}",
        subject_name=subject,
        headline=title[:_HEADLINE_MAX],
        source=f"web:{host or search_host}",
        categories=["web-osint"],
        subject_dob=None,
        subject_jurisdiction=jurisdiction,
        url=url,
        published=item.get("published"),
        snippet=item.get("snippet"),
    )
