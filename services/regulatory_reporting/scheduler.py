"""
services/regulatory_reporting/scheduler.py — n8n Cron Scheduler
IL-RRA-01 | Phase 14 | banxe-emi-stack

Triggers n8n workflows for scheduled regulatory report generation.
Uses SchedulerPort Protocol DI (InMemory for tests, N8nScheduler in prod).

n8n webhook: POST /webhook/regulatory-report-trigger
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import uuid

import httpx

from services.regulatory_reporting.models import (
    ScheduledReport,
    ScheduleFrequency,
)

logger = logging.getLogger(__name__)

# n8n cron expressions per frequency
_CRON_BY_FREQUENCY: dict[ScheduleFrequency, str] = {
    ScheduleFrequency.MONTHLY: "0 6 1 * *",  # 06:00 on 1st of month
    ScheduleFrequency.QUARTERLY: "0 6 1 1,4,7,10 *",  # 06:00 on 1st of Q
    ScheduleFrequency.ANNUALLY: "0 6 1 1 *",  # 06:00 on Jan 1st
    ScheduleFrequency.WEEKLY: "0 6 * * 1",  # 06:00 every Monday
}


def _make_schedule_id() -> str:
    return str(uuid.uuid4())


class N8nScheduler:
    """
    n8n-backed scheduler for recurring regulatory reports.

    Registers cron workflows in n8n via REST API.
    Falls back gracefully if n8n is unreachable (sandbox tolerance).

    Trust Zone: AMBER
    """

    def __init__(
        self,
        n8n_base_url: str = "http://localhost:5678",
        n8n_api_key: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = n8n_base_url.rstrip("/")
        self._api_key = n8n_api_key
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["X-N8N-API-KEY"] = self._api_key
        return h

    async def schedule(self, report: ScheduledReport) -> bool:
        cron = _CRON_BY_FREQUENCY.get(report.frequency, "0 6 1 * *")
        payload = {
            "name": f"regulatory-report-{report.report_type.value}-{report.entity_id}",
            "nodes": [
                {
                    "type": "n8n-nodes-base.cron",
                    "parameters": {"cronExpression": cron},
                    "name": "Cron Trigger",
                    "position": [240, 300],
                },
                {
                    "type": "n8n-nodes-base.httpRequest",
                    "parameters": {
                        "url": f"{self._base_url}/webhook/regulatory-report-trigger",
                        "method": "POST",
                        "bodyParameters": {
                            "parameters": [
                                {"name": "schedule_id", "value": report.id},
                                {"name": "report_type", "value": report.report_type.value},
                                {"name": "entity_id", "value": report.entity_id},
                                {"name": "template_version", "value": report.template_version},
                            ]
                        },
                    },
                    "name": "Trigger Report",
                    "position": [460, 300],
                },
            ],
            "active": report.is_active,
            "tags": ["regulatory", "automated", report.report_type.value],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/workflows",
                    json=payload,
                    headers=self._headers(),
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    logger.info(
                        "Scheduled n8n workflow %s for %s entity=%s",
                        data.get("id"),
                        report.report_type.value,
                        report.entity_id,
                    )
                    return True
                logger.warning("n8n schedule failed: %s %s", resp.status_code, resp.text[:200])
                return False
        except httpx.RequestError as exc:
            logger.warning("n8n unreachable — schedule not persisted: %s", exc)
            return False

    async def cancel(self, schedule_id: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.delete(
                    f"{self._base_url}/api/v1/workflows/{schedule_id}",
                    headers=self._headers(),
                )
                if resp.status_code in (200, 204):
                    logger.info("Cancelled n8n workflow %s", schedule_id)
                    return True
                logger.warning("n8n cancel failed: %s", resp.status_code)
                return False
        except httpx.RequestError as exc:
            logger.warning("n8n unreachable — cancel not confirmed: %s", exc)
            return False

    async def list_active(self, entity_id: str) -> list[ScheduledReport]:
        """Query n8n for active workflows tagged with entity_id."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/workflows",
                    params={"active": True, "tags": entity_id},
                    headers=self._headers(),
                )
                if resp.status_code != 200:
                    return []
                workflows = resp.json().get("data", [])
                results: list[ScheduledReport] = []
                for wf in workflows:
                    body = wf.get("nodes", [{}])[1].get("parameters", {})
                    params = {
                        p["name"]: p["value"]
                        for p in body.get("bodyParameters", {}).get("parameters", [])
                    }
                    from services.regulatory_reporting.models import ReportType  # noqa: PLC0415

                    results.append(
                        ScheduledReport(
                            id=params.get("schedule_id", wf.get("id", "")),
                            report_type=ReportType(params.get("report_type", "FIN060")),
                            entity_id=params.get("entity_id", entity_id),
                            frequency=ScheduleFrequency.MONTHLY,
                            next_run_at=datetime.now(UTC),
                            template_version=params.get("template_version", "v1"),
                            is_active=wf.get("active", True),
                            n8n_workflow_id=str(wf.get("id", "")),
                        )
                    )
                return results
        except httpx.RequestError:
            return []
