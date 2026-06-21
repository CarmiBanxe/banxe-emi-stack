"""services/abs/info_field.py — Advisory ABS info-field metadata surface (MIG genuine-gap #1).

Descriptive, config-as-data ABS **info-field metadata** (semantic port for the legacy
`abs-info-field.service.ts`). Advisory / sandbox / read-only: it describes field metadata (key, label,
type, group) — it holds NO live data, performs NO live integrations, calls NO Midaz LedgerPort, touches
NO KYC/KYB/AML, and mutates NO ledger/state. Fail-closed (unknown key -> None). No monetary numerics
(descriptive only); no float (I-01 trivially — there are no money values here).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

SANDBOX_SOURCE = "sandbox-mock"


class AbsFieldType(str, Enum):
    """Descriptive data-type of an ABS info-field (metadata only, not a value)."""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    ENUM = "enum"


@dataclass(frozen=True)
class AbsInfoFieldDescriptor:
    """Descriptive ABS info-field metadata (config-as-data; no live value, no numerics)."""

    field_key: str
    label: str
    field_type: AbsFieldType
    group: str
    source: str = SANDBOX_SOURCE


# Config-as-data descriptive field catalogue (sandbox; no live source, no balances).
_ABS_INFO_FIELDS: tuple[dict[str, object], ...] = (
    {
        "field_key": "customer_ref",
        "label": "Customer Reference",
        "field_type": AbsFieldType.STRING,
        "group": "customer",
    },
    {
        "field_key": "agreement_no",
        "label": "Agreement Number",
        "field_type": AbsFieldType.STRING,
        "group": "agreement",
    },
    {
        "field_key": "legal_entity_country",
        "label": "Legal Entity Country",
        "field_type": AbsFieldType.STRING,
        "group": "legal_entity",
    },
    {
        "field_key": "onboarding_status",
        "label": "Onboarding Status",
        "field_type": AbsFieldType.ENUM,
        "group": "lifecycle",
    },
    {
        "field_key": "agreement_active",
        "label": "Agreement Active",
        "field_type": AbsFieldType.BOOLEAN,
        "group": "agreement",
    },
)


class AbsInfoFieldPort(ABC):
    """Read-only advisory ABS info-field metadata contract (descriptive; fail-closed)."""

    @abstractmethod
    def list_fields(self) -> list[AbsInfoFieldDescriptor]: ...

    @abstractmethod
    def get_field(self, field_key: str) -> AbsInfoFieldDescriptor | None:
        """Return the descriptor for a field_key, or None if unknown (fail-closed)."""


class SandboxAbsInfoFieldProvider(AbsInfoFieldPort):
    """Sandbox config-as-data provider (mock-safe; no live integration, no Midaz, no KYC)."""

    def list_fields(self) -> list[AbsInfoFieldDescriptor]:
        return [AbsInfoFieldDescriptor(source=SANDBOX_SOURCE, **f) for f in _ABS_INFO_FIELDS]  # type: ignore[arg-type]

    def get_field(self, field_key: str) -> AbsInfoFieldDescriptor | None:
        return next(
            (f for f in self.list_fields() if f.field_key == field_key), None
        )  # fail-closed
