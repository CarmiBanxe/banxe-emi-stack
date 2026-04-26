"""
services/fatca_crs/hmrc_reporter.py
HMRC FATCA/CRS annual report generation (IL-HMR-01).
Integrates with SelfCertEngine (Phase 55A) to collect certifications.
I-01: all amounts Decimal strings.
I-24: ReportLog append-only.
I-27: generate + submit require CFO + MLRO dual sign-off (L4).
BT-012: submit_to_hmrc_gateway() raises NotImplementedError.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
from typing import Protocol

from services.fatca_crs.hmrc_models import (
    AccountHolder,
    FinancialInstitution,
    HMRCReport,
    HMRCSubmissionResult,
    HMRCValidationError,
    HMRCValidationResult,
    ReportableAccount,
)


class ReportStorePort(Protocol):
    def save(self, report: HMRCReport) -> None: ...
    def get_by_year(self, tax_year: int) -> HMRCReport | None: ...


class InMemoryReportStore:
    def __init__(self) -> None:
        self._reports: list[HMRCReport] = []  # I-24 append-only

    def save(self, report: HMRCReport) -> None:
        self._reports.append(report)

    def get_by_year(self, tax_year: int) -> HMRCReport | None:
        matches = [r for r in self._reports if r.tax_year == tax_year]
        return matches[-1] if matches else None


@dataclass
class HMRCHITLProposal:
    """I-27: HMRC report generation/submission requires CFO + MLRO dual sign-off."""

    proposal_id: str
    action: str
    tax_year: int
    requires_approval_from: list[str] = field(default_factory=lambda: ["CFO", "MLRO"])
    approved: bool = False
    proposed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


BLOCKED_JURISDICTIONS = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}

_DEFAULT_FI = FinancialInstitution(
    fi_id="banxe_emi_001",
    name="Banxe EMI Ltd",
    country="GB",
    giin="BANXE-EMI-GIIN",
)


class HMRCReporter:
    """HMRC FATCA/CRS annual report generator.

    I-01: all amounts as Decimal strings.
    I-24: report_log is append-only.
    I-27: generation and submission require CFO + MLRO.
    BT-012: submit_to_hmrc_gateway() raises NotImplementedError.
    """

    def __init__(
        self,
        store: ReportStorePort | None = None,
        fi: FinancialInstitution | None = None,
    ) -> None:
        self._store: ReportStorePort = store or InMemoryReportStore()
        self._fi = fi or _DEFAULT_FI
        self._report_log: list[dict] = []  # I-24 append-only
        self._proposals: list[HMRCHITLProposal] = []

    def generate_annual_report(
        self, tax_year: int, accounts: list[dict] | None = None
    ) -> HMRCReport | HMRCHITLProposal:
        """I-27: generation requires CFO + MLRO dual sign-off."""
        pid = f"HMRC_{hashlib.sha256(f'{tax_year}gen'.encode()).hexdigest()[:8]}"
        proposal = HMRCHITLProposal(
            proposal_id=pid,
            action=f"generate_annual_report_{tax_year}",
            tax_year=tax_year,
        )
        self._proposals.append(proposal)
        return proposal

    def _do_generate(self, tax_year: int, accounts: list[dict] | None = None) -> HMRCReport:
        """Internal generation -- called after HITL approval."""
        now = datetime.now(UTC).isoformat()
        report_id = "hmrc_" + hashlib.sha256(f"{tax_year}{now}".encode()).hexdigest()[:8]

        input_accounts = accounts or []
        fatca_accounts: list[ReportableAccount] = []
        crs_accounts: list[ReportableAccount] = []

        for acc in input_accounts:
            country = acc.get("country", "GB")
            if country in BLOCKED_JURISDICTIONS:
                continue  # I-02: skip blocked jurisdictions
            holder = AccountHolder(
                account_id=acc.get("account_id", f"ACC_{len(fatca_accounts):04d}"),
                customer_id=acc.get("customer_id", "UNKNOWN"),
                name=acc.get("name", "Unknown"),
                country_of_residence=country,
                tin=acc.get("tin", "0000000000"),
                us_person=acc.get("us_person", False),
            )
            reportable = ReportableAccount(
                account_id=holder.account_id,
                account_holder=holder,
                balance=str(Decimal(str(acc.get("balance", "0.00"))).quantize(Decimal("0.01"))),
                currency=acc.get("currency", "GBP"),
                reportable_jurisdiction=country,
                tax_year=tax_year,
            )
            if holder.us_person:
                fatca_accounts.append(reportable)
            else:
                crs_accounts.append(reportable)

        report = HMRCReport(
            report_id=report_id,
            tax_year=tax_year,
            fi=self._fi,
            fatca_accounts=fatca_accounts,
            crs_accounts=crs_accounts,
            generated_at=now,
        )
        self._store.save(report)
        self._report_log.append(
            {
                "event": "hmrc_report.generated",
                "report_id": report_id,
                "tax_year": tax_year,
                "total_accounts": len(fatca_accounts) + len(crs_accounts),
                "logged_at": now,
            }
        )
        return report

    def validate_report(self, report: HMRCReport) -> HMRCValidationResult:
        """Validate report against HMRC schema rules."""
        errors: list[HMRCValidationError] = []

        if report.tax_year < 2014:
            errors.append(
                HMRCValidationError(
                    field="tax_year",
                    message="FATCA/CRS reporting starts from 2014",
                )
            )
        if not report.fi.giin:
            errors.append(HMRCValidationError(field="fi.giin", message="GIIN is required"))

        for acc in report.fatca_accounts + report.crs_accounts:
            bal = Decimal(acc.balance)
            if bal < Decimal("0"):
                errors.append(
                    HMRCValidationError(
                        field=f"account.{acc.account_id}.balance",
                        message="Balance must be non-negative (I-01)",
                    )
                )
            if acc.account_holder.country_of_residence in BLOCKED_JURISDICTIONS:
                errors.append(
                    HMRCValidationError(
                        field=f"account.{acc.account_id}.country",
                        message=(
                            f"Blocked jurisdiction: "
                            f"{acc.account_holder.country_of_residence} (I-02)"
                        ),
                    )
                )

        return HMRCValidationResult(
            report_id=report.report_id,
            valid=len(errors) == 0,
            errors=errors,
        )

    def submit_to_hmrc_gateway(self, report: HMRCReport) -> HMRCSubmissionResult:
        """BT-012 stub: HMRC API submission requires registration."""
        raise NotImplementedError(
            "BT-012: HMRC Gateway submission not yet implemented. "
            "Requires HMRC API registration and credentials (P1 item)."
        )

    @property
    def report_log(self) -> list[dict]:
        return list(self._report_log)

    @property
    def proposals(self) -> list[HMRCHITLProposal]:
        return list(self._proposals)
