"""
services/transaction_monitor/alerts/explanation_engine.py — Explanation Engine
IL-RTM-01 | banxe-emi-stack

Generates human-readable explanations for AML alerts, referencing
Compliance KB citations (Part 1) for regulatory grounding.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from services.transaction_monitor.models.risk_score import RiskScore
from services.transaction_monitor.models.transaction import TransactionEvent

logger = logging.getLogger("banxe.transaction_monitor.explanation")


# ── KB Port (Protocol DI) ──────────────────────────────────────────────────


@runtime_checkable
class KBPort(Protocol):
    """Interface for Compliance KB queries (Part 1)."""

    def query_regulation(self, regulation_ref: str) -> str: ...


class InMemoryKBPort:
    """Test stub — returns deterministic regulation summaries."""

    def query_regulation(self, regulation_ref: str) -> str:
        summaries = {
            "EBA GL/2021/02 §4.2": "EMIs must apply risk-based monitoring with velocity controls.",
            "MLR 2017 Reg.33": "Suspicious transaction patterns must be investigated and reported.",
            "FATF Rec 16": "Wire transfers must include originator and beneficiary information.",
            "Banxe I-02": "Transactions involving sanctioned jurisdictions are hard-blocked.",
            "Banxe I-04": "EDD required for cumulative GBP 10,000+ (individual).",
        }
        for key, summary in summaries.items():
            if key in regulation_ref or regulation_ref in key:
                return summary
        return f"Regulatory basis: {regulation_ref}"


class HTTPKBPort:
    """Production KB port — queries /v1/kb/query."""

    def __init__(self, api_base: str = "http://localhost:8000") -> None:
        self._api_base = api_base

    def query_regulation(self, regulation_ref: str) -> str:
        import httpx

        with httpx.Client(base_url=self._api_base, timeout=10.0) as client:
            r = client.post(
                "/v1/kb/query",
                json={
                    "notebook_id": "emi-eu-aml",
                    "question": regulation_ref,
                    "max_citations": 3,
                },
            )
            if r.is_success:
                data = r.json()
                return data.get("answer", f"Regulatory basis: {regulation_ref}")
        return f"Regulatory basis: {regulation_ref}"


# ── Explanation Engine ─────────────────────────────────────────────────────


class ExplanationEngine:
    """Generates human-readable audit-trail explanations for AML alerts.

    Queries the Compliance KB to attach regulatory citations.
    """

    def __init__(self, kb_port: KBPort | None = None) -> None:
        self._kb = kb_port or InMemoryKBPort()

    def generate(
        self,
        event: TransactionEvent,
        risk_score: RiskScore,
        regulation_refs: list[str],
    ) -> str:
        """Generate a structured explanation for an alert.

        Format:
          ALERT: <severity> risk transaction detected
          Transaction: <id>
          Amount: GBP <amount>
          Risk Score: <score> (<classification>)
          Risk Factors: ...
          Regulatory Basis: ...
          Recommended: ...
        """
        severity = risk_score.classification.upper()
        top_factors = sorted(risk_score.factors, key=lambda f: f.contribution, reverse=True)[:5]

        lines = [
            f"ALERT: {severity} risk transaction detected",
            f"Transaction: {event.transaction_id}",
            f"Amount: {event.currency} {event.amount:,.2f}",
            f"Risk Score: {risk_score.score:.2f} ({risk_score.classification.upper()})",
            f"Sender: {event.sender_id} ({event.sender_jurisdiction})",
            "",
            "Risk Factors:",
        ]

        for i, factor in enumerate(top_factors, 1):
            lines.append(
                f"  {i}. {factor.name}: {factor.value:.2f} "
                f"(contribution: {factor.contribution:.2f})"
            )
            lines.append(f"     {factor.explanation}")
            if factor.regulation_ref:
                lines.append(f"     → {factor.regulation_ref}")

        if regulation_refs:
            lines += ["", "Regulatory Basis:"]
            for ref in regulation_refs[:3]:
                summary = self._kb.query_regulation(ref)
                lines.append(f"  • {ref}: {summary[:120]}")

        recommendation = self._recommendation(risk_score)
        lines += ["", f"Recommended: {recommendation}"]

        return "\n".join(lines)

    def extract_regulation_refs(self, risk_score: RiskScore) -> list[str]:
        """Extract unique regulation refs from risk factors."""
        refs: list[str] = []
        for factor in risk_score.factors:
            if factor.regulation_ref and factor.regulation_ref not in refs:
                refs.append(factor.regulation_ref)
        return refs

    @staticmethod
    def _recommendation(risk_score: RiskScore) -> str:
        if risk_score.classification == "critical":
            return "ESCALATE to MLRO immediately — potential SAR required"
        if risk_score.classification == "high":
            return "ESCALATE to analyst queue — review within 24h SLA"
        if risk_score.classification == "medium":
            return "REVIEW — auto-enriched, analyst review within 48h"
        return "AUTO-CLOSE — low risk, log and close"
