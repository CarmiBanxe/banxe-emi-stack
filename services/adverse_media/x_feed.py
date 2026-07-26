"""
services/adverse_media/x_feed.py — X (Twitter) adverse-media source adapter.

GAP-064 sibling of feed.py::OpenSanctionsAdjacencyFeed. Implements the
NegativeNewsFeed Protocol so X open-source intelligence can feed the SAME governed
adverse-media screening path (onboarding EDD + periodic monitoring) as any other
negative-news source — MLR 2017 Reg.28(3), FCA SYSC 6.3, Banxe I-04.

REGULATORY POSTURE (unchanged from the service): advisory ONLY. This feed only
SUPPLIES candidate articles; it makes NO decision. AdverseMediaService routes any
hit to MANDATORY MLRO HITL review (no auto-clear, no auto-block). X posts are an
UNVERIFIED open source — they can raise a review flag, never decide onboarding or
block a transaction on their own.

⚠️ SANDBOX / NON-PROD:
    Disabled by default. With no explicit opt-in it returns [] (safe stub, no network,
    no secrets) — identical degrade-to-[] contract as OpenSanctionsAdjacencyFeed.
    In SANDBOX this feed DOES NOT participate in screening or any customer decision.
    PROD ENABLEMENT REQUIRES, separately, all of:
      - compliance/MLRO sign-off that X is an approved adverse-media source,
      - a data-protection / lawful-basis assessment (UK GDPR) for screening
        individuals against social media,
      - X_ADVERSE_MEDIA_ENABLED=1 AND a valid X_BEARER_TOKEN in env (never in code),
      - re-issue of the SANDBOX ADRs (047/049/054/055) as ratified.
    Until then this adapter is inert.

SECRETS (I-SEC / ACCESS-AND-SECRETS): X_BEARER_TOKEN is read from env only, never
logged, never held in code. Subject names are NOT logged (R-SEC / PII).
"""

from __future__ import annotations

import logging
import os

import httpx

from services.adverse_media.models import AdverseMediaArticle

logger = logging.getLogger(__name__)

_X_RECENT_SEARCH = "https://api.twitter.com/2/tweets/search/recent"


class XAdverseMediaFeed:
    """Adverse-media candidate feed backed by X recent-search.

    SANDBOX-OFF by default: returns [] unless X_ADVERSE_MEDIA_ENABLED=1 AND a bearer
    token is present. Any error degrades to [] — a feed failure never breaks screening.
    Implements the NegativeNewsFeed Protocol (fetch(name, *, jurisdiction=None)).
    """

    def __init__(self, *, enabled: bool | None = None, timeout_s: float = 5.0) -> None:
        # explicit opt-in; default OFF (sandbox posture)
        env_on = os.environ.get("X_ADVERSE_MEDIA_ENABLED", "") == "1"
        self._enabled = env_on if enabled is None else enabled
        self._token = os.environ.get("X_BEARER_TOKEN", "")
        self._timeout_s = timeout_s

    def fetch(self, name: str, *, jurisdiction: str | None = None) -> list[AdverseMediaArticle]:
        # SANDBOX / not-enabled → inert, no network, no decision impact.
        if not self._enabled or not self._token:
            logger.info("X adverse-media feed disabled (sandbox) — no hits")  # no name logged
            return []
        # Negative-news oriented query; X is advisory only, results still go to MLRO HITL.
        query = f'"{name}" (fraud OR sanctions OR laundering OR scam OR investigation OR arrested)'
        params = {
            "query": query,
            "max_results": "10",
            "tweet.fields": "created_at,author_id,entities",
        }
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            with httpx.Client(timeout=self._timeout_s) as client:
                resp = client.get(_X_RECENT_SEARCH, params=params, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("X adverse-media feed error: %s", exc)  # no name/PII in log
            return []
        data = payload.get("data", []) if isinstance(payload, dict) else []
        return [_to_article(item, subject=name, jurisdiction=jurisdiction) for item in data]


def _to_article(
    item: dict, *, subject: str, jurisdiction: str | None
) -> AdverseMediaArticle:
    tid = str(item.get("id", ""))
    text = str(item.get("text", ""))
    return AdverseMediaArticle(
        article_id=f"x:{tid}",
        subject_name=subject,
        headline=text[:120],
        source="x.com",
        categories=["social-media-osint"],
        subject_dob=None,
        subject_jurisdiction=jurisdiction,
        url=f"https://x.com/i/web/status/{tid}" if tid else None,
        published=item.get("created_at"),
        snippet=text,
    )
