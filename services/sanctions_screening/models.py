from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
import hashlib
from typing import Protocol


class ScreeningResult(StrEnum):
    CLEAR = "clear"
    POSSIBLE_MATCH = "possible_match"
    CONFIRMED_MATCH = "confirmed_match"
    ERROR = "error"


class ListSource(StrEnum):
    OFSI = "ofsi"
    EU_CONSOLIDATED = "eu_consolidated"
    UN_CONSOLIDATED = "un_consolidated"
    US_OFAC = "us_ofac"
    FATF_GREYLIST = "fatf_greylist"
    INTERNAL = "internal"


class MatchConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EntityType(StrEnum):
    INDIVIDUAL = "individual"
    ORGANISATION = "organisation"
    VESSEL = "vessel"


class AlertStatus(StrEnum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    ESCALATED = "escalated"
    RESOLVED_TRUE = "resolved_true_positive"
    RESOLVED_FALSE = "resolved_false_positive"


@dataclass(frozen=True)
class ScreeningRequest:
    request_id: str
    entity_name: str
    entity_type: EntityType
    nationality: str
    date_of_birth: str | None
    requested_by: str
    requested_at: str


@dataclass(frozen=True)
class ScreeningHit:
    hit_id: str
    request_id: str
    list_source: ListSource
    match_confidence: MatchConfidence
    match_score: Decimal  # I-01: 0-100 Decimal
    matched_name: str
    matched_entity_id: str
    details: str


@dataclass(frozen=True)
class ScreeningReport:
    report_id: str
    request_id: str
    result: ScreeningResult
    hits: list[ScreeningHit] = field(default_factory=list)
    screened_at: str = ""
    notes: str = ""


@dataclass(frozen=True)
class SanctionsList:
    list_id: str
    source: ListSource
    version: str
    entry_count: int
    last_updated: str
    checksum: str  # I-12: SHA-256


@dataclass(frozen=True)
class AlertCase:
    alert_id: str
    request_id: str
    hit_id: str
    status: AlertStatus
    assigned_to: str
    created_at: str
    resolved_at: str | None = None
    resolution_notes: str | None = None


@dataclass
class HITLProposal:
    action: str
    entity_name: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


# Protocols
class ScreeningStore(Protocol):
    def save_request(self, req: ScreeningRequest) -> None: ...
    def get_request(self, request_id: str) -> ScreeningRequest | None: ...
    def save_report(self, report: ScreeningReport) -> None: ...
    def get_report(self, request_id: str) -> ScreeningReport | None: ...


class ListStore(Protocol):
    def get_list(self, source: ListSource) -> SanctionsList | None: ...
    def save_list(self, lst: SanctionsList) -> None: ...
    def get_entries(self, source: ListSource) -> list[dict]: ...


class AlertStore(Protocol):
    def append(self, alert: AlertCase) -> None: ...  # I-24: append-only
    def get(self, alert_id: str) -> AlertCase | None: ...
    def list_open(self) -> list[AlertCase]: ...
    def list_by_status(self, status: AlertStatus) -> list[AlertCase]: ...


class HitStore(Protocol):
    def append(self, hit: ScreeningHit) -> None: ...  # I-24
    def list_by_request(self, request_id: str) -> list[ScreeningHit]: ...


# InMemory stubs
class InMemoryScreeningStore:
    def __init__(self) -> None:
        self._requests: dict[str, ScreeningRequest] = {}
        self._reports: dict[str, ScreeningReport] = {}

    def save_request(self, req: ScreeningRequest) -> None:
        self._requests[req.request_id] = req

    def get_request(self, request_id: str) -> ScreeningRequest | None:
        return self._requests.get(request_id)

    def save_report(self, report: ScreeningReport) -> None:
        self._reports[report.request_id] = report

    def get_report(self, request_id: str) -> ScreeningReport | None:
        return self._reports.get(request_id)


class InMemoryListStore:
    def __init__(self) -> None:
        self._lists: dict[ListSource, SanctionsList] = {}
        self._entries: dict[ListSource, list[dict]] = {}
        self._lists[ListSource.OFSI] = SanctionsList(
            "lst_ofsi_001",
            ListSource.OFSI,
            "2026-04-01",
            5,
            "2026-04-01",
            hashlib.sha256(b"ofsi_seed").hexdigest(),
        )
        self._lists[ListSource.EU_CONSOLIDATED] = SanctionsList(
            "lst_eu_001",
            ListSource.EU_CONSOLIDATED,
            "2026-04-01",
            5,
            "2026-04-01",
            hashlib.sha256(b"eu_seed").hexdigest(),
        )
        self._entries[ListSource.OFSI] = [
            {"id": "ofsi_001", "name": "Ivan Petrov", "nationality": "RU", "type": "individual"},
            {
                "id": "ofsi_002",
                "name": "Sanctioned Corp Ltd",
                "nationality": "IR",
                "type": "organisation",
            },
            {"id": "ofsi_003", "name": "Test Vessel Alpha", "nationality": "KP", "type": "vessel"},
        ]
        self._entries[ListSource.EU_CONSOLIDATED] = [
            {
                "id": "eu_001",
                "name": "Vladimir Sanctions",
                "nationality": "RU",
                "type": "individual",
            },
            {
                "id": "eu_002",
                "name": "Frozen Assets GmbH",
                "nationality": "BY",
                "type": "organisation",
            },
        ]

    def get_list(self, source: ListSource) -> SanctionsList | None:
        return self._lists.get(source)

    def save_list(self, lst: SanctionsList) -> None:
        self._lists[lst.source] = lst

    def get_entries(self, source: ListSource) -> list[dict]:
        return self._entries.get(source, [])


class InMemoryAlertStore:
    def __init__(self) -> None:
        self._log: list[AlertCase] = []

    def append(self, alert: AlertCase) -> None:  # I-24
        self._log.append(alert)

    def get(self, alert_id: str) -> AlertCase | None:
        return next((a for a in self._log if a.alert_id == alert_id), None)

    def list_open(self) -> list[AlertCase]:
        return [a for a in self._log if a.status == AlertStatus.OPEN]

    def list_by_status(self, status: AlertStatus) -> list[AlertCase]:
        return [a for a in self._log if a.status == status]


class InMemoryHitStore:
    def __init__(self) -> None:
        self._log: list[ScreeningHit] = []

    def append(self, hit: ScreeningHit) -> None:  # I-24
        self._log.append(hit)

    def list_by_request(self, request_id: str) -> list[ScreeningHit]:
        return [h for h in self._log if h.request_id == request_id]
