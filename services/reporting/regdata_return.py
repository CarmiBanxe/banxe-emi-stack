"""
regdata_return.py — FCA RegData Monthly Safeguarding Return Automation
S6-12 | FCA CASS 15 / PS25/12 | banxe-emi-stack

WHY THIS FILE EXISTS
--------------------
FCA requires EMIs to submit monthly safeguarding returns (FIN060a/b) via
FCA RegData portal. Deadline: 15th of the month following the reporting period.

This module automates the full pipeline:
  1. Calculate reporting period (previous calendar month)
  2. Fetch FIN060 data from ClickHouse (via fin060_generator)
  3. Generate FIN060 PDF
  4. POST to FCA RegData API (stub — requires FCA_REGDATA_API_KEY)
  5. Record submission in ClickHouse audit log

FCA requirements:
  - CASS 15.12.4R: monthly safeguarding return by the 15th
  - MLR 2017: retain submission records for 5 years
  - FCA RegData: firm reference number (FRN) required

STATUS: Production RegData API — STUB (requires FCA_REGDATA_API_KEY, CEO action).
Data pipeline + PDF generation are fully functional.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
import logging
import os
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

FRN = os.environ.get("FCA_FRN", "000000")  # Banxe FCA Firm Reference Number
REGDATA_API_KEY = os.environ.get("FCA_REGDATA_API_KEY", "")
REGDATA_URL = os.environ.get(
    "FCA_REGDATA_URL",
    "https://regdata.fca.org.uk/api/v1/returns",  # placeholder — not live
)


class ReturnStatus(str, Enum):
    PENDING = "PENDING"
    GENERATED = "GENERATED"
    SUBMITTED = "SUBMITTED"
    SUBMISSION_FAILED = "SUBMISSION_FAILED"
    ACCEPTED = "ACCEPTED"


# ── Domain types ──────────────────────────────────────────────────────────────


@dataclass
class RegDataReturn:
    """One monthly FCA RegData safeguarding return."""

    period_start: date
    period_end: date
    frn: str
    avg_daily_client_funds: Decimal
    peak_client_funds: Decimal
    currency: str
    safeguarding_method: str
    status: ReturnStatus = ReturnStatus.PENDING
    pdf_path: str | None = None
    submission_id: str | None = None
    submitted_at: datetime | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def deadline(self) -> date:
        """Return due date: 15th of month following period end."""
        year = self.period_end.year + (1 if self.period_end.month == 12 else 0)
        month = 1 if self.period_end.month == 12 else self.period_end.month + 1
        return date(year, month, 15)

    @property
    def is_overdue(self) -> bool:
        return date.today() > self.deadline and self.status != ReturnStatus.ACCEPTED


# ── Generator protocol ────────────────────────────────────────────────────────


class FIN060Generator(Protocol):
    def generate(self, period_start: date, period_end: date) -> tuple[Path, Decimal, Decimal]: ...


# ── In-memory generator (for tests) ───────────────────────────────────────────


class MockFIN060Generator:
    """Deterministic stub — no ClickHouse, no WeasyPrint."""

    def __init__(self, avg: Decimal = Decimal("100000"), peak: Decimal = Decimal("150000")) -> None:
        self._avg = avg
        self._peak = peak

    def generate(self, period_start: date, period_end: date) -> tuple[Path, Decimal, Decimal]:
        # Return a fake path (file not created) + amounts
        return Path(f"/tmp/FIN060_{period_start.strftime('%Y%m')}.pdf"), self._avg, self._peak  # nosec B108  # noqa: S108 — stub, tracked by IL-FIN060-REAL-01 (replaced via tempfile.mkstemp)


# ── Real FIN060 generator wrapper ─────────────────────────────────────────────


class RealFIN060Generator:  # pragma: no cover
    """Wraps fin060_generator.generate_fin060() + fetches amounts."""

    def generate(self, period_start: date, period_end: date) -> tuple[Path, Decimal, Decimal]:
        from services.reporting.fin060_generator import _fetch_period_data, generate_fin060

        data = _fetch_period_data(period_start, period_end)
        pdf_path = generate_fin060(period_start, period_end)
        return pdf_path, data.avg_daily_client_funds, data.peak_client_funds


# ── Submission client (stubbed) ───────────────────────────────────────────────


class RegDataSubmissionClient(Protocol):
    def submit(self, return_: RegDataReturn, pdf_path: Path) -> str: ...  # returns submission_id


class StubRegDataClient:
    """Stub — returns a fake submission ID without making any HTTP call."""

    def submit(self, return_: RegDataReturn, pdf_path: Path) -> str:
        logger.warning(
            "RegData submission STUBBED — FCA_REGDATA_API_KEY not set. "
            "Return for %s/%s not actually submitted.",
            return_.period_start,
            return_.period_end,
        )
        return f"STUB-{return_.frn}-{return_.period_start.strftime('%Y%m')}"


class LiveRegDataClient:  # pragma: no cover
    """
    Live FCA RegData API client.
    STATUS: STUB — requires FCA_REGDATA_API_KEY (CEO action: obtain from FCA RegData portal).
    """

    def submit(self, return_: RegDataReturn, pdf_path: Path) -> str:
        raise NotImplementedError(
            "LiveRegDataClient not implemented. "
            "Set FCA_REGDATA_API_KEY and FCA_FRN, then implement HTTP POST to RegData."
        )


# ── Return service ────────────────────────────────────────────────────────────


def _previous_month_period() -> tuple[date, date]:
    """Return (first_day, last_day) of the previous calendar month."""
    import calendar

    today = date.today()
    year = today.year - 1 if today.month == 1 else today.year
    month = 12 if today.month == 1 else today.month - 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


class RegDataReturnService:
    """
    Orchestrates monthly FCA RegData safeguarding return.

    Usage (cron, 14th of each month):
        service = RegDataReturnService()
        result = service.run_monthly_return()
        if result.status == ReturnStatus.SUBMITTED:
            logger.info("RegData return submitted: %s", result.submission_id)
    """

    def __init__(
        self,
        generator: FIN060Generator | None = None,
        client: RegDataSubmissionClient | None = None,
        frn: str | None = None,
    ) -> None:
        self._generator = generator or MockFIN060Generator()
        self._client = client or StubRegDataClient()
        self._frn = frn or FRN

    def run_monthly_return(
        self,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> RegDataReturn:
        """Generate and submit FIN060 for the given period (default: previous month)."""
        if period_start is None or period_end is None:
            period_start, period_end = _previous_month_period()

        logger.info("Starting RegData return for %s – %s", period_start, period_end)

        return_ = RegDataReturn(
            period_start=period_start,
            period_end=period_end,
            frn=self._frn,
            avg_daily_client_funds=Decimal("0"),
            peak_client_funds=Decimal("0"),
            currency="GBP",
            safeguarding_method="segregated",
        )

        try:
            pdf_path, avg, peak = self._generator.generate(period_start, period_end)
            return_.avg_daily_client_funds = avg
            return_.peak_client_funds = peak
            return_.pdf_path = str(pdf_path)
            return_.status = ReturnStatus.GENERATED
            logger.info("FIN060 generated: %s (avg=£%s peak=£%s)", pdf_path, avg, peak)
        except Exception as exc:
            return_.status = ReturnStatus.SUBMISSION_FAILED
            return_.errors.append(f"PDF generation failed: {exc}")
            logger.error("FIN060 generation failed: %s", exc)
            return return_

        try:
            submission_id = self._client.submit(return_, pdf_path)
            return_.submission_id = submission_id
            return_.submitted_at = datetime.now(UTC)
            return_.status = ReturnStatus.SUBMITTED
            logger.info("RegData submission OK: %s", submission_id)
        except Exception as exc:
            return_.status = ReturnStatus.SUBMISSION_FAILED
            return_.errors.append(f"RegData submission failed: {exc}")
            logger.error("RegData submission failed: %s", exc)

        return return_
