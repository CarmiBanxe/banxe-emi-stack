"""
services/compliance_calendar/models.py
IL-CCD-01 | Phase 42 | banxe-emi-stack

Domain models, protocols, and in-memory stubs for Compliance Calendar & Deadline Tracker.
Trust Zone: RED
Protocol DI: Port (Protocol) → InMemory stub (tests) → Real adapter (production)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol

# ── Enums ────────────────────────────────────────────────────────────────────


class DeadlineType(str, Enum):
    FCA_RETURN = "FCA_RETURN"
    AML_REVIEW = "AML_REVIEW"
    BOARD_REPORT = "BOARD_REPORT"
    AUDIT = "AUDIT"
    LICENCE_RENEWAL = "LICENCE_RENEWAL"
    CUSTOM = "CUSTOM"


class DeadlineStatus(str, Enum):
    UPCOMING = "UPCOMING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    OVERDUE = "OVERDUE"
    ESCALATED = "ESCALATED"


class Priority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RecurrencePattern(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"


class ReminderChannel(str, Enum):
    EMAIL = "EMAIL"
    SLACK = "SLACK"
    TELEGRAM = "TELEGRAM"
    WEBHOOK = "WEBHOOK"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ComplianceDeadline:
    id: str
    title: str
    deadline_type: DeadlineType
    status: DeadlineStatus
    priority: Priority
    due_date: date
    owner: str
    description: str
    created_at: datetime
    recurrence: RecurrencePattern | None = None
    evidence_hash: str | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True)
class DeadlineReminder:
    id: str
    deadline_id: str
    channel: ReminderChannel
    scheduled_at: datetime
    message: str
    acknowledged: bool = False
    sent_at: datetime | None = None


@dataclass(frozen=True)
class ComplianceTask:
    id: str
    deadline_id: str
    title: str
    assigned_to: str
    progress: int
    status: str
    created_at: datetime
    notes: str = ""
    completed_at: datetime | None = None


@dataclass(frozen=True)
class CalendarView:
    period_start: date
    period_end: date
    deadlines: list[ComplianceDeadline]
    overdue_count: int
    upcoming_count: int
    completed_count: int


@dataclass(frozen=True)
class DeadlineReport:
    generated_at: datetime
    period: str
    total: int
    on_time: int
    late: int
    compliance_score: Decimal
    by_type: dict
    critical_overdue: list[str] = field(default_factory=list)


# ── Protocols ────────────────────────────────────────────────────────────────


class DeadlineStore(Protocol):
    def save_deadline(self, d: ComplianceDeadline) -> None: ...
    def get_deadline(self, id: str) -> ComplianceDeadline | None: ...
    def list_all(self) -> list[ComplianceDeadline]: ...
    def list_by_type(self, t: DeadlineType) -> list[ComplianceDeadline]: ...


class ReminderStore(Protocol):
    def save_reminder(self, r: DeadlineReminder) -> None: ...
    def get_reminder(self, id: str) -> DeadlineReminder | None: ...
    def list_pending(self, deadline_id: str) -> list[DeadlineReminder]: ...


class TaskStore(Protocol):
    def save_task(self, t: ComplianceTask) -> None: ...
    def get_task(self, id: str) -> ComplianceTask | None: ...
    def list_by_deadline(self, deadline_id: str) -> list[ComplianceTask]: ...


class CalendarStore(Protocol):
    def save_view(self, v: CalendarView) -> None: ...
    def get_view(self, period: str) -> CalendarView | None: ...


# ── InMemory Stubs ────────────────────────────────────────────────────────────


class InMemoryDeadlineStore:
    def __init__(self) -> None:
        self._deadlines: dict[str, ComplianceDeadline] = {}
        self._seed()

    def _seed(self) -> None:
        now = datetime.now(UTC)
        seed_deadlines = [
            ComplianceDeadline(
                id="dl-fca-fin060-q1",
                title="FIN060 Q1 2026",
                deadline_type=DeadlineType.FCA_RETURN,
                status=DeadlineStatus.UPCOMING,
                priority=Priority.CRITICAL,
                due_date=date(2026, 4, 30),
                owner="CFO",
                description="FCA Financial Return FIN060 for Q1 2026",
                created_at=now,
            ),
            ComplianceDeadline(
                id="dl-aml-annual-2026",
                title="Annual AML Review 2026",
                deadline_type=DeadlineType.AML_REVIEW,
                status=DeadlineStatus.UPCOMING,
                priority=Priority.HIGH,
                due_date=date(2026, 6, 30),
                owner="MLRO",
                description="Annual AML programme review per MLR 2017",
                created_at=now,
            ),
            ComplianceDeadline(
                id="dl-board-q1-risk",
                title="Q1 Board Risk Report",
                deadline_type=DeadlineType.BOARD_REPORT,
                status=DeadlineStatus.UPCOMING,
                priority=Priority.HIGH,
                due_date=date(2026, 4, 25),
                owner="CRO",
                description="Board-level risk report for Q1 2026",
                created_at=now,
            ),
            ComplianceDeadline(
                id="dl-consumer-duty-audit",
                title="Consumer Duty Annual Assessment",
                deadline_type=DeadlineType.AUDIT,
                status=DeadlineStatus.UPCOMING,
                priority=Priority.MEDIUM,
                due_date=date(2026, 7, 31),
                owner="CCO",
                description="Annual Consumer Duty assessment per PS22/9",
                created_at=now,
            ),
            ComplianceDeadline(
                id="dl-mlr-annual-return",
                title="MLR Annual Return",
                deadline_type=DeadlineType.LICENCE_RENEWAL,
                status=DeadlineStatus.UPCOMING,
                priority=Priority.CRITICAL,
                due_date=date(2026, 9, 30),
                owner="MLRO",
                description="Money Laundering Regulations annual return to HMRC",
                created_at=now,
            ),
        ]
        for dl in seed_deadlines:
            self._deadlines[dl.id] = dl

    def save_deadline(self, d: ComplianceDeadline) -> None:
        self._deadlines[d.id] = d

    def get_deadline(self, id: str) -> ComplianceDeadline | None:
        return self._deadlines.get(id)

    def list_all(self) -> list[ComplianceDeadline]:
        return list(self._deadlines.values())

    def list_by_type(self, t: DeadlineType) -> list[ComplianceDeadline]:
        return [d for d in self._deadlines.values() if d.deadline_type == t]


class InMemoryReminderStore:
    def __init__(self) -> None:
        self._reminders: dict[str, DeadlineReminder] = {}

    def save_reminder(self, r: DeadlineReminder) -> None:
        self._reminders[r.id] = r

    def get_reminder(self, id: str) -> DeadlineReminder | None:
        return self._reminders.get(id)

    def list_pending(self, deadline_id: str) -> list[DeadlineReminder]:
        return [
            r
            for r in self._reminders.values()
            if r.deadline_id == deadline_id and r.sent_at is None
        ]

    def list_by_deadline(self, deadline_id: str) -> list[DeadlineReminder]:
        return [r for r in self._reminders.values() if r.deadline_id == deadline_id]


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, ComplianceTask] = {}

    def save_task(self, t: ComplianceTask) -> None:
        self._tasks[t.id] = t

    def get_task(self, id: str) -> ComplianceTask | None:
        return self._tasks.get(id)

    def list_by_deadline(self, deadline_id: str) -> list[ComplianceTask]:
        return [t for t in self._tasks.values() if t.deadline_id == deadline_id]

    def list_by_assignee(self, assigned_to: str) -> list[ComplianceTask]:
        return [t for t in self._tasks.values() if t.assigned_to == assigned_to]


class InMemoryCalendarStore:
    def __init__(self) -> None:
        self._views: dict[str, CalendarView] = {}

    def save_view(self, v: CalendarView) -> None:
        key = f"{v.period_start}_{v.period_end}"
        self._views[key] = v

    def get_view(self, period: str) -> CalendarView | None:
        return self._views.get(period)
