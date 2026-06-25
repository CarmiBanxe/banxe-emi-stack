"""
services/gabriel/regdata_gabriel_adapter.py
RegDataGabrielAdapter — production GabrielSubmissionPort implementation.

Routes HITL-approved SubmissionRecords to the correct FCA RegData client:
  FIN060        → FIN060Generator.generate() + RegDataSubmissionClient.submit()
  BREACH_REPORT → FCARegDataClientProtocol.submit_breach_notification()

Usage:
  adapter = RegDataGabrielAdapter(breach_client, fin060_client, fin060_generator)
  adapter.register_breach_event(event)   # call when breach draft is created
  governor.approve(submission_id, "MLRO-Alice", adapter)  # HITL gate

I-01: discrepancy / amounts are Decimal (sourced from BreachEvent.shortfall).
I-27: This adapter is ONLY called through ReturnsGovernor.approve() — never autonomously.
"""

from __future__ import annotations

from dataclasses import replace as _replace
from datetime import UTC, date, datetime, timedelta
import logging

from services.gabriel.gabriel_models import (
    GabrielReturnStatus,
    GabrielReturnType,
    SubmissionRecord,
)
from services.recon.breach_detector import BreachRecord
from services.recon.breach_notify_port import BreachEvent
from services.recon.fca_regdata_client import FCARegDataClientProtocol
from services.reporting.regdata_return import (
    FRN,
    FIN060Generator,
    RegDataReturn,
    RegDataSubmissionClient,
)

logger = logging.getLogger(__name__)

_DEFAULT_CURRENCY = "GBP"
_DEFAULT_SAFEGUARDING_METHOD = "STATUTORY_TRUST"


class RegDataGabrielAdapter:
    """GabrielSubmissionPort — routes approved records to FCA RegData.

    Args:
        breach_client: FCA RegData client for breach notifications.
        fin060_client: FCA RegData client for monthly FIN060 submissions.
        fin060_generator: Generates FIN060 PDF from period dates.
        frn: FCA Firm Reference Number (defaults to FCA_FRN env var).
    """

    def __init__(
        self,
        breach_client: FCARegDataClientProtocol,
        fin060_client: RegDataSubmissionClient,
        fin060_generator: FIN060Generator,
        frn: str = FRN,
    ) -> None:
        self._breach_client = breach_client
        self._fin060_client = fin060_client
        self._fin060_generator = fin060_generator
        self._frn = frn
        self._breach_events: dict[str, BreachEvent] = {}  # recon_id → BreachEvent

    def register_breach_event(self, event: BreachEvent) -> None:
        """Pre-register a BreachEvent so BREACH_REPORT submit() can build FCA payload."""
        self._breach_events[event.recon_id] = event

    def submit(self, record: SubmissionRecord) -> SubmissionRecord:
        """Implement GabrielSubmissionPort: route by return_type to FCA client."""
        if record.return_type == GabrielReturnType.FIN060:
            return self._submit_fin060(record)
        if record.return_type == GabrielReturnType.BREACH_REPORT:
            return self._submit_breach(record)
        raise ValueError(f"Unsupported return_type: {record.return_type}")

    # ── Internal: FIN060 ──────────────────────────────────────────────────────

    def _submit_fin060(self, record: SubmissionRecord) -> SubmissionRecord:
        year = int(record.return_period[:4])
        month = int(record.return_period[5:7])
        period_start = date(year, month, 1)
        if month == 12:
            period_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            period_end = date(year, month + 1, 1) - timedelta(days=1)

        pdf_path, avg, peak = self._fin060_generator.generate(period_start, period_end)
        ret = RegDataReturn(
            period_start=period_start,
            period_end=period_end,
            frn=self._frn,
            avg_daily_client_funds=avg,
            peak_client_funds=peak,
            currency=_DEFAULT_CURRENCY,
            safeguarding_method=_DEFAULT_SAFEGUARDING_METHOD,
        )
        submission_id = self._fin060_client.submit(ret, pdf_path)
        logger.info(
            "FIN060 submitted to FCA RegData: period=%s ref=%s", record.return_period, submission_id
        )
        return _replace(
            record,
            status=GabrielReturnStatus.SUBMITTED,
            submitted_at=datetime.now(UTC).isoformat(),
            submission_ref=submission_id,
        )

    # ── Internal: BREACH_REPORT ───────────────────────────────────────────────

    def _submit_breach(self, record: SubmissionRecord) -> SubmissionRecord:
        event = self._breach_events.get(record.source_recon_id or "")
        if event is None:
            raise KeyError(
                f"No BreachEvent registered for source_recon_id={record.source_recon_id!r}. "
                f"Call register_breach_event() before approve()."
            )
        breach = BreachRecord(
            account_id=event.recon_id,
            account_type="SAFEGUARDING",
            currency=event.currency,
            discrepancy=event.shortfall,
            days_outstanding=1,  # initial FCA notification; streak tracked by ClickHouse
            first_seen=date.fromisoformat(event.recon_date),
            latest_date=date.fromisoformat(event.recon_date),
        )
        result = self._breach_client.submit_breach_notification(breach)
        logger.info(
            "BREACH_REPORT submitted to FCA RegData: recon_id=%s fca_ref=%s",
            event.recon_id,
            result.fca_reference,
        )
        return _replace(
            record,
            status=GabrielReturnStatus.SUBMITTED,
            submitted_at=result.submitted_at,
            submission_ref=result.fca_reference or None,
        )
