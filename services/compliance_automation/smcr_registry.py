"""
services/compliance_automation/smcr_registry.py
SMCRRegistryPort Protocol + InMemorySMCRRegistry (IL-GOV-01).

I-24: Append-only stores.
"""

from __future__ import annotations

from typing import Protocol

from services.compliance_automation.smcr_models import (
    BreachReport,
    CertifiedPerson,
    SeniorManager,
)


class SMCRRegistryPort(Protocol):
    """Port for SMCR data storage."""

    def register_senior_manager(self, manager: SeniorManager) -> SeniorManager: ...

    def get_senior_manager(self, person_id: str) -> SeniorManager | None: ...

    def list_senior_managers(self) -> list[SeniorManager]: ...

    def register_certified_person(self, person: CertifiedPerson) -> CertifiedPerson: ...

    def get_certified_person(self, person_id: str) -> CertifiedPerson | None: ...

    def list_certified_persons(self) -> list[CertifiedPerson]: ...

    def file_breach(self, report: BreachReport) -> BreachReport: ...

    def list_breaches(self, status: str | None = None) -> list[BreachReport]: ...


class InMemorySMCRRegistry:
    """In-memory stub implementing SMCRRegistryPort for tests."""

    def __init__(self) -> None:
        self._managers: dict[str, SeniorManager] = {}
        self._certified: dict[str, CertifiedPerson] = {}
        self._breaches: list[BreachReport] = []

    def register_senior_manager(self, manager: SeniorManager) -> SeniorManager:
        if manager.person_id in self._managers:
            raise ValueError(f"Senior manager {manager.person_id!r} already registered")
        self._managers[manager.person_id] = manager
        return manager

    def get_senior_manager(self, person_id: str) -> SeniorManager | None:
        return self._managers.get(person_id)

    def list_senior_managers(self) -> list[SeniorManager]:
        return list(self._managers.values())

    def register_certified_person(self, person: CertifiedPerson) -> CertifiedPerson:
        if person.person_id in self._certified:
            raise ValueError(f"Certified person {person.person_id!r} already registered")
        self._certified[person.person_id] = person
        return person

    def get_certified_person(self, person_id: str) -> CertifiedPerson | None:
        return self._certified.get(person_id)

    def list_certified_persons(self) -> list[CertifiedPerson]:
        return list(self._certified.values())

    def file_breach(self, report: BreachReport) -> BreachReport:
        self._breaches.append(report)
        return report

    def list_breaches(self, status: str | None = None) -> list[BreachReport]:
        if status is None:
            return list(self._breaches)
        return [b for b in self._breaches if b.status.value == status]
