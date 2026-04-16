"""
services/regulatory_reporting/regulatory_reporting_agent.py — Main Orchestration Agent
IL-RRA-01 | Phase 14 | banxe-emi-stack

Orchestrates: generate → validate → audit → (optionally) submit regulatory reports.
Autonomy: L2 (generates + validates automatically; submission requires human approval).

FCA refs: SUP 16.12, SYSC 9.1.1R, POCA 2002 s.330
I-27: AI PROPOSES submission — human DECIDES to submit.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import uuid

from services.regulatory_reporting.audit_trail import (
    make_failed_entry,
    make_generated_entry,
    make_submitted_entry,
    make_validated_entry,
)
from services.regulatory_reporting.models import (
    AuditTrailPort,
    RegulatorGatewayPort,
    RegulatorTarget,
    ReportRequest,
    ReportResult,
    ReportStatus,
    ReportType,
    ScheduledReport,
    SchedulerPort,
    ValidatorPort,
    XMLGeneratorPort,
)

logger = logging.getLogger(__name__)


class RegulatoryReportingAgent:
    """
    Main orchestration agent for regulatory reporting.

    Flow: generate XML → validate (structural + XSD) → audit → propose submission.

    Autonomy: L2 — auto-generates and validates; submission is HITL (I-27).
    Trust Zone: AMBER
    """

    def __init__(
        self,
        xml_generator: XMLGeneratorPort,
        validator: ValidatorPort,
        audit_trail: AuditTrailPort,
        scheduler: SchedulerPort,
        regulator_gateway: RegulatorGatewayPort,
    ) -> None:
        self._generator = xml_generator
        self._validator = validator
        self._audit = audit_trail
        self._scheduler = scheduler
        self._gateway = regulator_gateway

    async def generate_report(
        self,
        request: ReportRequest,
        financial_data: dict,
        actor: str,
    ) -> ReportResult:
        """
        Generate and validate a regulatory report.

        Does NOT submit — submission is L4 (human only via submit_report()).
        Returns a result with status VALIDATED (ready to submit) or FAILED.
        """
        report_id = str(uuid.uuid4())

        # Step 1: Generate XML
        try:
            xml_content = await self._generator.generate(request, financial_data)
        except Exception as exc:  # noqa: BLE001
            error_msg = f"XML generation failed: {exc}"
            logger.error("Report generation failed for %s: %s", request.report_type, exc)
            entry = make_failed_entry(request, report_id, error_msg, actor)
            await self._audit.append(entry)
            return ReportResult(
                request_id=report_id,
                report_type=request.report_type,
                status=ReportStatus.FAILED,
                xml_content=None,
                pdf_content=None,
                validation_errors=[error_msg],
                submission_ref=None,
                generated_at=datetime.now(UTC),
            )

        # Step 2: Create draft result
        result = ReportResult(
            request_id=report_id,
            report_type=request.report_type,
            status=ReportStatus.DRAFT,
            xml_content=xml_content,
            pdf_content=None,
            validation_errors=[],
            submission_ref=None,
            generated_at=datetime.now(UTC),
        )

        # Audit generation event
        gen_entry = make_generated_entry(request, result, actor)
        await self._audit.append(gen_entry)

        # Step 3: Validate XML
        validation = await self._validator.validate(xml_content, request.report_type)

        # Step 4: Update result with validation status
        final_status = ReportStatus.VALIDATED if validation.is_valid else ReportStatus.FAILED
        result = ReportResult(
            request_id=report_id,
            report_type=request.report_type,
            status=final_status,
            xml_content=xml_content,
            pdf_content=None,
            validation_errors=validation.errors,
            submission_ref=None,
            generated_at=result.generated_at,
        )

        # Audit validation event
        val_entry = make_validated_entry(request, result, validation, actor)
        await self._audit.append(val_entry)

        if validation.is_valid:
            logger.info(
                "Report %s VALIDATED for %s entity=%s — ready to submit (L4 gate)",
                report_id,
                request.report_type.value,
                request.entity_id,
            )
        else:
            logger.warning(
                "Report %s FAILED validation: %d errors",
                report_id,
                len(validation.errors),
            )

        return result

    async def submit_report(
        self,
        request: ReportRequest,
        result: ReportResult,
        target: RegulatorTarget,
        actor: str,
    ) -> ReportResult:
        """
        Submit a validated report to the regulator portal.

        I-27: This is L4 — must be explicitly triggered by an authorised human.
        Caller is responsible for ensuring HITL approval has been obtained.
        """
        if not result.is_ready_to_submit:
            raise ValueError(
                f"Report {result.request_id} is not ready to submit "
                f"(status={result.status}, errors={result.validation_errors})"
            )

        try:
            submission_ref = await self._gateway.submit(result, target)
        except Exception as exc:  # noqa: BLE001
            error_msg = f"Submission to {target.value} failed: {exc}"
            logger.error("Submission failed for %s: %s", result.request_id, exc)
            fail_entry = make_failed_entry(
                request,
                result.request_id,
                error_msg,
                actor,
                event_type="report.submission_failed",
            )
            await self._audit.append(fail_entry)
            raise

        # Audit submission event (SYSC 9 record)
        sub_entry = make_submitted_entry(request, result, submission_ref, actor, target)
        await self._audit.append(sub_entry)

        submitted = ReportResult(
            request_id=result.request_id,
            report_type=result.report_type,
            status=ReportStatus.SUBMITTED,
            xml_content=result.xml_content,
            pdf_content=result.pdf_content,
            validation_errors=[],
            submission_ref=submission_ref,
            generated_at=result.generated_at,
            submitted_at=datetime.now(UTC),
            regulator_target=target,
        )
        logger.info(
            "Report %s SUBMITTED to %s — ref=%s",
            result.request_id,
            target.value,
            submission_ref,
        )
        return submitted

    async def schedule_report(
        self,
        report: ScheduledReport,
        actor: str,
    ) -> bool:
        """Schedule recurring report via n8n. Returns True if registered."""
        success = await self._scheduler.schedule(report)
        if success:
            logger.info(
                "Scheduled %s for entity=%s frequency=%s (actor=%s)",
                report.report_type.value,
                report.entity_id,
                report.frequency.value,
                actor,
            )
        else:
            logger.warning(
                "Failed to schedule %s for entity=%s",
                report.report_type.value,
                report.entity_id,
            )
        return success

    async def cancel_schedule(self, schedule_id: str, actor: str) -> bool:
        """Cancel a scheduled report. Returns True if successfully cancelled."""
        success = await self._scheduler.cancel(schedule_id)
        logger.info("Cancelled schedule %s (actor=%s, success=%s)", schedule_id, actor, success)
        return success

    async def get_audit_log(
        self,
        report_type: ReportType | None = None,
        entity_id: str | None = None,
        days: int = 30,
    ) -> list[dict]:
        """Return audit entries as dicts (for API serialisation)."""
        entries = await self._audit.query(
            report_type=report_type,
            entity_id=entity_id,
            days=days,
        )
        return [
            {
                "id": e.id,
                "event_type": e.event_type,
                "report_type": e.report_type.value,
                "report_id": e.report_id,
                "entity_id": e.entity_id,
                "actor": e.actor,
                "status": e.status.value,
                "details": e.details,
                "created_at": e.created_at.isoformat(),
                "regulator_target": e.regulator_target.value if e.regulator_target else None,
            }
            for e in entries
        ]
