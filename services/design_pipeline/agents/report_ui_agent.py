"""
services/design_pipeline/agents/report_ui_agent.py — Report UI Agent
IL-D2C-01 | BANXE EMI AI Bank

Generates FCA report layouts and SAR report UI components:
  - FIN060a/b monthly return display views
  - SAR (Suspicious Activity Report) review screens
  - Safeguarding reconciliation dashboards
  - Audit trail viewer UI

FCA references:
  - FIN060 (FCA Gabriel/RegData monthly return)
  - CASS 15 safeguarding report UI
  - POCA 2002 s.330 (SAR disclosure UI requirements)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from services.design_pipeline.models import Framework, GenerationResult
from services.design_pipeline.orchestrator import DesignToCodeOrchestrator

logger = logging.getLogger("banxe.design_pipeline.agents.report_ui")

_REPORT_SYSTEM_PROMPT = """You are an expert regulatory reporting UI developer for BANXE AI Bank.

REPORT UI REQUIREMENTS:
1. Accessibility: WCAG 2.1 AA — all report data must be screen-reader accessible
2. Data integrity: amounts shown must use Decimal precision (no rounding in display)
3. Date/time: always show UTC timezone explicitly; convert to local for display only
4. Print: all report views must be printable with proper page breaks
5. Export: CSV/PDF export buttons must be present on all data tables
6. Audit: all report views must log access to ClickHouse (EU AI Act Art.14 oversight)
7. Consumer Duty: report language must be clear and jargon-free where customer-facing
"""


@dataclass
class ReportSection:
    """A section within a regulatory report."""

    id: str
    title: str
    data_fields: list[str]
    is_monetary: bool = True
    regulatory_basis: str = ""


class ReportUIAgent:
    """
    Generates FCA regulatory report UI components.

    Produces view-only report layouts from dbt model outputs.
    All monetary values are displayed as Decimal strings (no float).
    """

    def __init__(
        self,
        orchestrator: DesignToCodeOrchestrator,
        penpot_file_id: str = "",
        default_framework: Framework = Framework.REACT,
    ) -> None:
        self._orchestrator = orchestrator
        self._file_id = penpot_file_id
        self._framework = default_framework

    async def generate_fin060_view(self, framework: Framework | None = None) -> GenerationResult:
        """
        Generate FIN060a/b monthly return display view.

        Renders safeguarding balances per CASS 15 requirements.
        FIN060a: average safeguarded funds
        FIN060b: peak safeguarded funds
        """
        prompt = (
            f"{_REPORT_SYSTEM_PROMPT}\n\n"
            f"Generate a FIN060 monthly return viewer component:\n"
            f"1. Header: reporting period, entity name, FCA reference number\n"
            f"2. FIN060a table: average daily safeguarded funds by currency\n"
            f"3. FIN060b table: peak safeguarded funds by currency\n"
            f"4. Submission status badge (DRAFT/SUBMITTED/ACCEPTED)\n"
            f"5. Submit to RegData button (disabled once SUBMITTED)\n"
            f"6. Download PDF button\n"
            f"7. Audit trail: who generated, when, last modified\n"
            f"All monetary amounts shown as Decimal strings with 2dp and GBP/EUR prefix.\n"
        )
        return await self._generate_screen("fin060_view", prompt, framework)

    async def generate_sar_review_screen(
        self, framework: Framework | None = None
    ) -> GenerationResult:
        """
        Generate SAR (Suspicious Activity Report) review screen.

        POCA 2002 s.330: MLRO must review and approve before NCA submission.
        L4 authority required — UI enforces MLRO-only access.
        """
        prompt = (
            f"{_REPORT_SYSTEM_PROMPT}\n\n"
            f"Generate a SAR review screen for MLRO:\n"
            f"1. Case summary: customer ID (masked), transaction IDs, risk score\n"
            f"2. Timeline of suspicious activity events\n"
            f"3. MLRO decision buttons: SUBMIT TO NCA | DISMISS with reason\n"
            f"4. Mandatory reasoning field (min 100 characters) before decision\n"
            f"5. Consent to disclose checkbox (POCA 2002 s.338)\n"
            f"6. Warning banner: 'Tipping off is a criminal offence (POCA 2002 s.333A)'\n"
            f"7. Audit log showing all views of this SAR\n"
            f"Access: MLRO only — show error page for any other role.\n"
        )
        return await self._generate_screen("sar_review", prompt, framework)

    async def generate_recon_dashboard(
        self, framework: Framework | None = None
    ) -> GenerationResult:
        """
        Generate safeguarding reconciliation dashboard.

        CASS 15: daily recon status must be immediately visible.
        Shows MATCHED/DISCREPANCY/PENDING per account.
        """
        prompt = (
            f"{_REPORT_SYSTEM_PROMPT}\n\n"
            f"Generate a CASS 15 reconciliation dashboard:\n"
            f"1. Date picker (default: today)\n"
            f"2. Status summary cards: MATCHED (green), DISCREPANCY (red), PENDING (amber)\n"
            f"3. Per-account table: account ID, type, internal balance, external balance, delta\n"
            f"4. Discrepancy detail modal (click on DISCREPANCY row)\n"
            f"5. FCA breach threshold indicator (£0 = no breach, >£0 = breach alert)\n"
            f"6. Run Reconciliation button (triggers POST /v1/recon/run)\n"
            f"7. Export CSV button\n"
        )
        return await self._generate_screen("recon_dashboard", prompt, framework)

    async def generate_audit_trail_viewer(
        self, framework: Framework | None = None
    ) -> GenerationResult:
        """Generate audit trail viewer for ClickHouse event data."""
        prompt = (
            f"{_REPORT_SYSTEM_PROMPT}\n\n"
            f"Generate an audit trail viewer component:\n"
            f"1. Filters: date range, event type, user, account ID\n"
            f"2. Paginated table: timestamp (UTC), event type, user, entity, changes\n"
            f"3. Expandable row for full event payload (JSON viewer)\n"
            f"4. Export to CSV / download as PDF\n"
            f"5. Immutability badge: 'Append-only audit log — no modifications possible'\n"
        )
        return await self._generate_screen("audit_trail_viewer", prompt, framework)

    async def _generate_screen(
        self, screen_type: str, prompt: str, framework: Framework | None
    ) -> GenerationResult:
        fw = framework or self._framework
        mitosis_jsx = await self._orchestrator._llm.agenerate(prompt)
        compiled = self._orchestrator._generator.compile(mitosis_jsx, fw)
        return GenerationResult(
            component_id=f"report-{screen_type}",
            framework=fw,
            code=compiled,
            mitosis_jsx=mitosis_jsx,
            model_used=self._orchestrator._llm.model_name,
        )
