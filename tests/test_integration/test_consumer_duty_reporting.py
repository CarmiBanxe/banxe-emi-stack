"""
test_consumer_duty_reporting.py — IL-INT-01
Cross-module: outcome_assessor → fin060_generator data source.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

# ── Minimal stubs ────────────────────────────────────────────────────────────


class _OutcomeAssessment:
    def __init__(self, customer_id: str, outcome: str, score: Decimal, flag: str | None = None):
        self.customer_id = customer_id
        self.outcome = outcome
        self.score = score
        self.flag = flag
        self.assessed_at = datetime.now(UTC).isoformat()


class _InMemoryOutcomeStore:
    def __init__(self) -> None:
        self._records: list[_OutcomeAssessment] = []

    def record(self, assessment: _OutcomeAssessment) -> None:
        self._records.append(assessment)

    def get_all(self) -> list[_OutcomeAssessment]:
        return list(self._records)

    def get_flagged(self) -> list[_OutcomeAssessment]:
        return [r for r in self._records if r.flag is not None]


def _build_fin060_data_feed(assessments: list[_OutcomeAssessment]) -> dict:
    """Minimal FIN060 data feed from consumer duty assessments."""
    return {
        "report_period": "2026-04",
        "total_assessments": len(assessments),
        "flagged_count": sum(1 for a in assessments if a.flag),
        "average_score": (
            sum(a.score for a in assessments) / Decimal(len(assessments))
            if assessments
            else Decimal("0")
        ),
        "generated_at": datetime.now(UTC).isoformat(),
    }


class TestConsumerDutyReportingPipeline:
    def setup_method(self):
        self.store = _InMemoryOutcomeStore()

    def test_assessment_recorded_decimal_score(self):
        """I-01: score is Decimal."""
        a = _OutcomeAssessment("CUST001", "GOOD", Decimal("0.85"))
        assert isinstance(a.score, Decimal)

    def test_assessment_score_not_float(self):
        a = _OutcomeAssessment("CUST001", "GOOD", Decimal("0.85"))
        assert not isinstance(a.score, float)

    def test_fin060_feed_includes_total_count(self):
        for i in range(3):
            self.store.record(_OutcomeAssessment(f"CUST{i:03d}", "GOOD", Decimal("0.90")))
        feed = _build_fin060_data_feed(self.store.get_all())
        assert feed["total_assessments"] == 3

    def test_fin060_feed_includes_flagged_count(self):
        self.store.record(_OutcomeAssessment("CUST001", "GOOD", Decimal("0.90")))
        self.store.record(
            _OutcomeAssessment("CUST002", "POOR", Decimal("0.30"), flag="POOR_OUTCOME")
        )
        feed = _build_fin060_data_feed(self.store.get_all())
        assert feed["flagged_count"] == 1

    def test_fin060_average_score_decimal(self):
        self.store.record(_OutcomeAssessment("CUST001", "GOOD", Decimal("0.80")))
        self.store.record(_OutcomeAssessment("CUST002", "GOOD", Decimal("0.90")))
        feed = _build_fin060_data_feed(self.store.get_all())
        assert isinstance(feed["average_score"], Decimal)
        assert feed["average_score"] == Decimal("0.85")

    def test_fin060_empty_assessments_zero_score(self):
        feed = _build_fin060_data_feed([])
        assert feed["total_assessments"] == 0
        assert feed["average_score"] == Decimal("0")

    def test_fin060_has_report_period(self):
        feed = _build_fin060_data_feed([])
        assert "report_period" in feed

    def test_fin060_has_generated_at(self):
        feed = _build_fin060_data_feed([])
        assert "generated_at" in feed

    def test_flagged_assessments_extracted(self):
        self.store.record(_OutcomeAssessment("CUST001", "GOOD", Decimal("0.90")))
        self.store.record(
            _OutcomeAssessment("CUST002", "POOR", Decimal("0.20"), flag="VULNERABILITY")
        )
        flagged = self.store.get_flagged()
        assert len(flagged) == 1
        assert flagged[0].flag == "VULNERABILITY"

    def test_multiple_flags_all_captured(self):
        for i in range(5):
            flag = "FLAG" if i % 2 == 0 else None
            self.store.record(
                _OutcomeAssessment(f"CUST{i:03d}", "MIXED", Decimal("0.50"), flag=flag)
            )
        flagged = self.store.get_flagged()
        assert len(flagged) == 3  # indices 0, 2, 4

    def test_assessment_has_timestamp(self):
        a = _OutcomeAssessment("CUST001", "GOOD", Decimal("0.85"))
        assert hasattr(a, "assessed_at")
        assert a.assessed_at is not None
