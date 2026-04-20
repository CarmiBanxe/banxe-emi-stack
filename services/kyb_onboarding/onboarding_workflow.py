from __future__ import annotations

from datetime import UTC, datetime

from services.kyb_onboarding.models import ApplicationStore

WORKFLOW_STAGES = ["doc_check", "ubo_verify", "sanctions", "risk", "decision"]
SLA_BUSINESS_DAYS = 5

# In-memory workflow state (per application_id)
_workflow_state: dict[str, dict] = {}


def _business_days_since(start_iso: str) -> int:
    try:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        days = 0
        current = start
        while current < now:
            if current.weekday() < 5:
                days += 1
            current = current.replace(day=current.day + 1)
        return days
    except Exception:
        return 0


class OnboardingWorkflow:
    def __init__(self, app_store: ApplicationStore) -> None:
        self._apps = app_store

    def start_workflow(self, application_id: str) -> dict:
        now = datetime.now(UTC).isoformat()
        state = {
            "application_id": application_id,
            "stage": "doc_check",
            "started_at": now,
            "stages_completed": [],
            "timeline": [{"stage": "doc_check", "started_at": now, "status": "in_progress"}],
        }
        _workflow_state[application_id] = state
        return {"stage": "doc_check", "started_at": now}

    def advance_stage(
        self,
        application_id: str,
        current_stage: str,
        passed: bool,
        notes: str = "",
    ) -> dict:
        state = _workflow_state.get(application_id, {})
        now = datetime.now(UTC).isoformat()
        if not passed:
            state.setdefault("timeline", []).append(
                {"stage": current_stage, "failed_at": now, "notes": notes}
            )
            _workflow_state[application_id] = state
            return {"stage": current_stage, "status": "failed", "notes": notes}

        completed = state.get("stages_completed", [])
        if current_stage not in completed:
            completed.append(current_stage)
        state["stages_completed"] = completed

        idx = WORKFLOW_STAGES.index(current_stage) if current_stage in WORKFLOW_STAGES else -1
        if idx >= 0 and idx + 1 < len(WORKFLOW_STAGES):
            next_stage = WORKFLOW_STAGES[idx + 1]
        else:
            next_stage = "decision"

        state["stage"] = next_stage
        state.setdefault("timeline", []).append(
            {"stage": current_stage, "completed_at": now, "notes": notes}
        )
        _workflow_state[application_id] = state
        return {"stage": next_stage, "status": "advanced", "notes": notes}

    def get_workflow_status(self, application_id: str) -> dict:
        state = _workflow_state.get(application_id)
        if not state:
            return {"application_id": application_id, "status": "not_started"}
        completed = state.get("stages_completed", [])
        current = state.get("stage", WORKFLOW_STAGES[0])
        pending = [s for s in WORKFLOW_STAGES if s not in completed and s != current]
        return {
            "application_id": application_id,
            "current_stage": current,
            "stages_completed": completed,
            "stages_pending": pending,
        }

    def get_timeline(self, application_id: str) -> list[dict]:
        state = _workflow_state.get(application_id, {})
        return state.get("timeline", [])

    def calculate_sla_remaining(self, application_id: str) -> int:
        """Returns business days remaining (negative if overdue)."""
        app = self._apps.get(application_id)
        if app is None:
            return SLA_BUSINESS_DAYS
        elapsed = _business_days_since(app.submitted_at)
        return SLA_BUSINESS_DAYS - elapsed
