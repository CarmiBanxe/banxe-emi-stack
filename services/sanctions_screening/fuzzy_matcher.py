from __future__ import annotations

from decimal import Decimal
from difflib import SequenceMatcher

from services.sanctions_screening.models import MatchConfidence

LOW_THRESHOLD = Decimal("40")  # I-01
MEDIUM_THRESHOLD = Decimal("65")  # I-01
HIGH_THRESHOLD = Decimal("85")  # I-01

_WEIGHTS_NAME = Decimal("0.6")
_WEIGHTS_DOB = Decimal("0.3")
_WEIGHTS_NAT = Decimal("0.1")


class FuzzyMatcher:
    def __init__(self) -> None:
        self._low = LOW_THRESHOLD
        self._medium = MEDIUM_THRESHOLD
        self._high = HIGH_THRESHOLD

    def match_name(self, name_a: str, name_b: str) -> Decimal:  # I-01
        ratio = SequenceMatcher(None, name_a.lower(), name_b.lower()).ratio()
        return Decimal(str(ratio * 100)).quantize(Decimal("0.01"))

    def match_dob(self, dob_a: str, dob_b: str) -> bool:
        """Exact YYYY-MM-DD match."""
        return dob_a.strip() == dob_b.strip()

    def match_nationality(self, nat_a: str, nat_b: str) -> bool:
        """Exact 2-letter ISO match."""
        return nat_a.strip().upper() == nat_b.strip().upper()

    def match_address(
        self,
        postcode_a: str,
        country_a: str,
        postcode_b: str,
        country_b: str,
    ) -> Decimal:
        pc_score = self.match_name(postcode_a, postcode_b)
        country_match = (
            Decimal("100") if self.match_nationality(country_a, country_b) else Decimal("0")
        )
        return (pc_score + country_match) / Decimal("2")

    def calculate_composite_score(
        self,
        name_score: Decimal,
        dob_match: bool,
        nat_match: bool,
    ) -> Decimal:
        """Weights: name=0.6, dob=0.3, nationality=0.1 (all Decimal, I-01)."""
        dob_score = Decimal("100") if dob_match else Decimal("0")
        nat_score = Decimal("100") if nat_match else Decimal("0")
        composite = name_score * _WEIGHTS_NAME + dob_score * _WEIGHTS_DOB + nat_score * _WEIGHTS_NAT
        return composite.quantize(Decimal("0.01"))

    def configure_thresholds(
        self,
        low: Decimal,
        medium: Decimal,
        high: Decimal,
    ) -> None:
        self._low = low
        self._medium = medium
        self._high = high

    def classify_confidence(self, score: Decimal) -> MatchConfidence:
        if score < self._medium:
            return MatchConfidence.LOW
        if score < self._high:
            return MatchConfidence.MEDIUM
        return MatchConfidence.HIGH
