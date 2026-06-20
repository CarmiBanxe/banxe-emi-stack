"""
services/adverse_media/matcher.py — NLP entity match (name + DOB + jurisdiction)
GAP-064 | IMPL-1 | banxe-emi-stack

Reuses services.sanctions_screening.fuzzy_matcher (I-01 weighted composite) —
does NOT reimplement structured screening (watchman/yente live there).
"""

from __future__ import annotations

from decimal import Decimal

from services.adverse_media.models import AdverseMediaArticle, AdverseMediaHit
from services.customer.customer_port import CustomerProfile
from services.sanctions_screening.fuzzy_matcher import FuzzyMatcher

# MEDIUM-confidence composite (I-01) — adverse-media is advisory, so we err toward review.
DEFAULT_HIT_THRESHOLD = Decimal("65")


def subject_identity(profile: CustomerProfile) -> tuple[str, str | None, str | None]:
    """Return (full_name, dob_iso, jurisdiction) for the customer's screenable subject."""
    if profile.individual is not None:
        ind = profile.individual
        return (
            f"{ind.first_name} {ind.last_name}",
            ind.date_of_birth.isoformat() if ind.date_of_birth else None,
            ind.nationality,
        )
    if profile.company is not None:
        co = profile.company
        return (co.company_name, None, co.country_of_incorporation)
    return (profile.customer_id, None, None)


class AdverseMediaMatcher:
    """Match adverse-media articles to a customer profile via fuzzy composite score."""

    def __init__(self, threshold: Decimal = DEFAULT_HIT_THRESHOLD) -> None:
        self._fuzzy = FuzzyMatcher()
        self._threshold = threshold

    def find_hits(
        self, profile: CustomerProfile, articles: list[AdverseMediaArticle]
    ) -> list[AdverseMediaHit]:
        name, dob, nationality = subject_identity(profile)
        hits: list[AdverseMediaHit] = []
        for article in articles:
            name_score = self._fuzzy.match_name(name, article.subject_name)
            dob_match = bool(
                dob and article.subject_dob and self._fuzzy.match_dob(dob, article.subject_dob)
            )
            nat_match = bool(
                nationality
                and article.subject_jurisdiction
                and self._fuzzy.match_nationality(nationality, article.subject_jurisdiction)
            )
            composite = self._fuzzy.calculate_composite_score(name_score, dob_match, nat_match)
            if composite >= self._threshold:
                hits.append(
                    AdverseMediaHit(
                        article=article,
                        name_score=name_score,
                        dob_match=dob_match,
                        nat_match=nat_match,
                        composite_score=composite,
                        confidence=self._fuzzy.classify_confidence(composite),
                    )
                )
        return hits
