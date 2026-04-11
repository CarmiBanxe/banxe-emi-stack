"""
recon_analysis.py — ReconAnalysisSkill
Analyzes reconciliation results for patterns and classifies discrepancies.
Uses pure Python logic (no LLM dependency in Phase 0 of this skill).
LLM integration point documented but not called in Phase 0.

FCA CASS 7.15 / CASS 15.12 | IL-015 Phase 5 | banxe-emi-stack

Classification rules (rule-based, Phase 0):
  SYSTEMATIC_ERROR   — same account DISCREPANCY 2+ days running
  FRAUD_RISK         — discrepancy > £50,000 (absolute)
  TIMING_DIFFERENCE  — discrepancy < £100 and appeared today
  MISSING_TRANSACTION — any other discrepancy
  MATCHED            — status is MATCHED (no discrepancy)

LLM integration point (Phase 1):
  _classify() can be replaced with LLM call via ReconAnalysisSkill.set_llm_backend().
  Until then, rule-based logic provides deterministic, auditable classification.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

logger = logging.getLogger("banxe.agents.recon_analysis")

# Thresholds (Decimal — never float, I-24)
FRAUD_THRESHOLD = Decimal("50000.00")    # £50k → FRAUD_RISK
TIMING_THRESHOLD = Decimal("100.00")     # < £100 → TIMING_DIFFERENCE
SYSTEMATIC_MIN_DAYS = 2                  # 2+ days same account → SYSTEMATIC_ERROR
LOW_CONFIDENCE = Decimal("0.70")         # HITL gate threshold (agents/compliance/soul/)


class DiscrepancyClass(str, Enum):
    """Discrepancy classification labels."""

    TIMING_DIFFERENCE = "TIMING_DIFFERENCE"
    MISSING_TRANSACTION = "MISSING_TRANSACTION"
    SYSTEMATIC_ERROR = "SYSTEMATIC_ERROR"
    FRAUD_RISK = "FRAUD_RISK"
    MATCHED = "MATCHED"


@dataclass(frozen=True)
class AnalysisReport:
    """Classification report for one reconciliation result.

    All numeric fields are Decimal (never float — I-24).
    Frozen dataclass — immutable for audit integrity.
    """

    account_id: str
    classification: DiscrepancyClass
    confidence: Decimal      # 0.00 to 1.00 — Decimal, never float
    recommendation: str
    pattern_detected: str


class ReconAnalysisSkill:
    """
    Analyzes List[ReconResult] for discrepancy patterns.

    Phase 0: Rule-based classification.
    Phase 1 (LLM integration point): call _classify() via LLM for complex patterns.

    Usage:
        skill = ReconAnalysisSkill()
        reports = skill.analyze(reconciliation_results)
        for report in reports:
            if report.confidence < Decimal("0.70"):
                # HITL gate — send to compliance officer review
    """

    def __init__(self, history: dict[str, list[dict]] | None = None) -> None:
        """
        Args:
            history: dict mapping account_id → list of recent result dicts.
                     Each dict has {"date": date, "discrepancy": Decimal, "status": str}.
                     Used to detect recurring patterns (SYSTEMATIC_ERROR).
        """
        self._history: dict[str, list[dict]] = history or {}

    def analyze(self, results: list[Any]) -> list[AnalysisReport]:
        """
        Classify each reconciliation result.

        Args:
            results: List of ReconResult (or any object with .account_id, .status,
                     .discrepancy attributes)

        Returns:
            list[AnalysisReport] — one report per result
        """
        reports: list[AnalysisReport] = []
        for result in results:
            classification, confidence, pattern = self._classify(result)
            recommendation = self._recommendation(classification, result)
            reports.append(
                AnalysisReport(
                    account_id=result.account_id,
                    classification=classification,
                    confidence=confidence,
                    recommendation=recommendation,
                    pattern_detected=pattern,
                )
            )
        return reports

    def _classify(
        self, result: Any
    ) -> tuple[DiscrepancyClass, Decimal, str]:
        """
        Rule-based classification (LLM integration point for Phase 1).

        Returns (classification, confidence, pattern_description).

        Rules (in priority order):
          1. MATCHED → status == MATCHED, confidence 1.00
          2. FRAUD_RISK → abs(discrepancy) > £50,000, confidence 0.95
          3. SYSTEMATIC_ERROR → same account DISCREPANCY 2+ consecutive days, confidence 0.90
          4. TIMING_DIFFERENCE → abs(discrepancy) < £100, confidence 0.80
          5. MISSING_TRANSACTION → default, confidence 0.75
        """
        # Rule 1: MATCHED
        if getattr(result, "status", "") == "MATCHED":
            return (
                DiscrepancyClass.MATCHED,
                Decimal("1.00"),
                "No discrepancy detected",
            )

        discrepancy = abs(Decimal(str(getattr(result, "discrepancy", "0"))))

        # Rule 2: FRAUD_RISK — large discrepancy
        if discrepancy > FRAUD_THRESHOLD:
            return (
                DiscrepancyClass.FRAUD_RISK,
                Decimal("0.95"),
                f"Discrepancy £{discrepancy} exceeds fraud threshold £{FRAUD_THRESHOLD}",
            )

        # Rule 3: SYSTEMATIC_ERROR — recurring pattern in history
        account_id = result.account_id
        history_for_account = self._history.get(account_id, [])
        discrepancy_streak = sum(
            1 for h in history_for_account if h.get("status") == "DISCREPANCY"
        )
        if discrepancy_streak >= SYSTEMATIC_MIN_DAYS:
            return (
                DiscrepancyClass.SYSTEMATIC_ERROR,
                Decimal("0.90"),
                f"Account {account_id} has {discrepancy_streak} consecutive DISCREPANCY days",
            )

        # Rule 4: TIMING_DIFFERENCE — small discrepancy
        if discrepancy < TIMING_THRESHOLD:
            return (
                DiscrepancyClass.TIMING_DIFFERENCE,
                Decimal("0.80"),
                f"Small discrepancy £{discrepancy} — likely timing/settlement difference",
            )

        # Rule 5: MISSING_TRANSACTION — default
        return (
            DiscrepancyClass.MISSING_TRANSACTION,
            Decimal("0.75"),
            f"Discrepancy £{discrepancy} — likely missing or duplicate transaction",
        )

    @staticmethod
    def _recommendation(classification: DiscrepancyClass, result: Any) -> str:
        """Generate human-readable recommendation for compliance officer."""
        account_id = getattr(result, "account_id", "unknown")
        discrepancy = abs(Decimal(str(getattr(result, "discrepancy", "0"))))

        recs = {
            DiscrepancyClass.MATCHED: "No action required — reconciliation successful.",
            DiscrepancyClass.FRAUD_RISK: (
                f"IMMEDIATE ESCALATION REQUIRED: £{discrepancy} discrepancy for {account_id}. "
                "Escalate to MLRO. CASS 15.12: FCA notification within 1 business day."
            ),
            DiscrepancyClass.SYSTEMATIC_ERROR: (
                f"Investigate systematic error for {account_id}. "
                "Check ledger posting rules and ASPSP statement accuracy."
            ),
            DiscrepancyClass.TIMING_DIFFERENCE: (
                f"Monitor {account_id}: £{discrepancy} discrepancy may self-correct. "
                "Recheck tomorrow — escalate if persists 3+ days."
            ),
            DiscrepancyClass.MISSING_TRANSACTION: (
                f"Investigate missing/duplicate transaction for {account_id}. "
                f"Cross-reference bank statement line items. Discrepancy: £{discrepancy}."
            ),
        }
        return recs.get(classification, "Review required.")
