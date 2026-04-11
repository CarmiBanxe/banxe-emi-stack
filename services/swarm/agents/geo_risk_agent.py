"""
services/swarm/agents/geo_risk_agent.py — Geographic Risk Agent
IL-ARL-01 | banxe-emi-stack

Assesses jurisdiction risk based on FATF greylist, blacklist,
EU high-risk third country, and OFAC sanctions.
"""

from __future__ import annotations

import logging
import time

from services.agent_routing.models import AgentTask
from services.agent_routing.schemas import AgentResponse
from services.swarm.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# I-02: Hard-blocked jurisdictions
_SANCTIONED: frozenset[str] = frozenset({"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"})

# I-03: FATF greylist (23 countries) — requires EDD
_FATF_GREYLIST: frozenset[str] = frozenset(
    {
        "BJ",
        "BF",
        "CM",
        "CD",
        "HT",
        "IR",
        "LY",
        "ML",
        "MZ",
        "MM",
        "NG",
        "PK",
        "PH",
        "SA",
        "SN",
        "ZA",
        "SS",
        "SY",
        "TZ",
        "VN",
        "YE",
        "AE",
        "UG",
    }
)

# High-risk third countries per EU AML Directive
_EU_HIGH_RISK: frozenset[str] = frozenset(
    {
        "AF",
        "BS",
        "BB",
        "BF",
        "KH",
        "KY",
        "CD",
        "HT",
        "JM",
        "JO",
        "ML",
        "MZ",
        "MM",
        "NI",
        "PK",
        "PH",
        "SN",
        "SS",
        "SY",
        "TT",
        "TZ",
        "UG",
        "VN",
        "YE",
        "ZW",
    }
)


class GeoRiskAgent(BaseAgent):
    """Geographic and jurisdictional risk assessment."""

    @property
    def agent_name(self) -> str:
        return "geo_risk_agent"

    @property
    def signal_type(self) -> str:
        return "geo_risk"

    async def analyze(self, task: AgentTask) -> AgentResponse:
        t_start = time.monotonic()
        ctx = task.risk_context
        payload = task.payload

        jurisdiction = task.jurisdiction.upper()
        beneficiary_country = payload.get("beneficiary_country", "").upper()
        cross_border = ctx.get("cross_border", False)

        # Check primary jurisdiction
        risk, signals, evidence = self._assess_country(jurisdiction)

        # Check beneficiary country if different
        if beneficiary_country and beneficiary_country != jurisdiction:
            b_risk, b_signals, b_evidence = self._assess_country(beneficiary_country)
            risk = max(risk, b_risk)
            signals.extend([f"beneficiary: {s}" for s in b_signals])
            evidence.extend(b_evidence)

        if cross_border and risk > 0.2:
            risk = min(risk + 0.1, 1.0)
            signals.append("cross-border transfer increases risk")

        hint: str
        if risk >= 0.9:
            hint = "block"
        elif risk >= 0.5:
            hint = "warning"
        else:
            hint = "clear"

        return AgentResponse(
            agent_name=self.agent_name,
            case_id=task.task_id,
            signal_type=self.signal_type,
            risk_score=round(risk, 4),
            confidence=0.92,
            decision_hint=hint,
            reason_summary="; ".join(signals)
            if signals
            else f"Jurisdiction {jurisdiction!r} low risk",
            evidence_refs=evidence,
            token_cost=0,
            latency_ms=int((time.monotonic() - t_start) * 1000),
        )

    @staticmethod
    def _assess_country(country: str) -> tuple[float, list[str], list[str]]:
        """Return (risk_score, signals, evidence_refs) for a country code."""
        if country in _SANCTIONED:
            return 1.0, [f"SANCTIONED jurisdiction {country!r} (I-02)"], ["invariant_I-02"]
        if country in _FATF_GREYLIST:
            return (
                0.65,
                [f"FATF greylist: {country!r} — EDD required (I-03)"],
                ["fatf_greylist", "invariant_I-03"],
            )
        if country in _EU_HIGH_RISK:
            return 0.55, [f"EU high-risk third country: {country!r}"], ["eu_aml_directive"]
        return 0.1, [], []
