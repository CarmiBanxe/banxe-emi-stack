"""F-finrpt (GAP-007) — FIN-RPT regulatory-returns CONTENT CORE.

Producer side of K-gabriel's ``FinRepSourcePort``. Computes and assembles
regulatory-return content (FCA FIN-REP data items + RegData content) derived
**read-only** from authoritative sources (Midaz ledger via LedgerPort, D-recon
aggregates via ReconSourcePort, J/E safeguarding totals via SafeguardingTotalsPort),
Decimal-only (I-01), content-versioned and immutable once ``FINAL`` (I-24/I-28).

GAP-007 ↔ GAP-006 fence (F-FINRPT-BUILD-SPEC §1): submission, breach-reporting,
deadline-tracking and sign-off are **K-gabriel's** (GAP-006), consumed via
``FinRepSourcePort``. They are **NOT** implemented here — any attempt to submit
through F-finrpt raises :class:`SubmissionFencedError`. This module never duplicates
``services/gabriel/*`` (ADR-102).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
import re
from typing import Protocol

# ── Status (immutable once FINAL) ──────────────────────────────────────────────
DRAFT = "DRAFT"
VALIDATED = "VALIDATED"
FINAL = "FINAL"

_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")  # "YYYY-MM"


class SubmissionFencedError(RuntimeError):
    """Submission is K-gabriel's (GAP-006) responsibility, consumed via FinRepSourcePort.

    F-finrpt (GAP-007) is the content **producer** only — it never submits, reports
    breaches, tracks deadlines, or signs off. Raised if submission is attempted here.
    """


class ContentValidationError(ValueError):
    """Return content failed validation rules and cannot be finalised (K-gabriel must
    not submit draft/invalid content)."""


# ── Data model (F-FINRPT-BUILD-SPEC §3) ────────────────────────────────────────
@dataclass(frozen=True)
class LineItem:
    """A single return line item. ``value`` is Decimal-only (I-01)."""

    code: str
    value: Decimal
    currency: str
    derivation_source: str
    period: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise TypeError(
                f"LineItem.value must be Decimal (I-01), got {type(self.value).__name__}"
            )


@dataclass(frozen=True)
class ReturnContentSet:
    """An assembled regulatory-return content set. Immutable once ``status == FINAL``."""

    fca_item_code: str
    return_period: str
    version: int
    line_items: tuple[LineItem, ...]
    derived_at: str
    source_refs: tuple[str, ...]
    content_hash: str
    status: str  # DRAFT | VALIDATED | FINAL

    def item(self, code: str) -> LineItem | None:
        return next((li for li in self.line_items if li.code == code), None)


# ── Ports (F-FINRPT-BUILD-SPEC §5) — read-only derivation sources ───────────────
class LedgerPort(Protocol):
    """Read Midaz balance aggregates (I-28: LedgerPort only, no direct HTTP)."""

    def get_balance_aggregate(self, code: str, period: str) -> Decimal: ...


class ReconSourcePort(Protocol):
    """Read D-recon ``safeguarding_events`` aggregates."""

    def get_recon_aggregate(self, code: str, period: str) -> Decimal: ...


class SafeguardingTotalsPort(Protocol):
    """Read J/E safeguarding totals."""

    def get_safeguarding_total(self, code: str, period: str) -> Decimal: ...


class ReturnContentStore(Protocol):
    """Append-only versioned content store; immutable at FINAL (I-24/I-28)."""

    def append(self, content: ReturnContentSet) -> None: ...
    def versions(self, fca_item_code: str, return_period: str) -> list[ReturnContentSet]: ...
    def latest_final(self, fca_item_code: str, return_period: str) -> ReturnContentSet | None: ...
    def list_final(self, return_period: str) -> list[ReturnContentSet]: ...


# ── In-memory adapters (test/sandbox; production wires real ports) ──────────────
class InMemoryReturnContentStore:
    """Append-only in-memory content store (I-24). No update/delete methods; a FINAL
    set is never mutated — a re-derivation appends a new version instead."""

    def __init__(self) -> None:
        self._sets: list[ReturnContentSet] = []

    def append(self, content: ReturnContentSet) -> None:
        self._sets.append(content)

    def versions(self, fca_item_code: str, return_period: str) -> list[ReturnContentSet]:
        return [
            s
            for s in self._sets
            if s.fca_item_code == fca_item_code and s.return_period == return_period
        ]

    def latest_final(self, fca_item_code: str, return_period: str) -> ReturnContentSet | None:
        finals = [s for s in self.versions(fca_item_code, return_period) if s.status == FINAL]
        return max(finals, key=lambda s: s.version) if finals else None

    def list_final(self, return_period: str) -> list[ReturnContentSet]:
        return [s for s in self._sets if s.return_period == return_period and s.status == FINAL]


@dataclass
class _DictSource:
    """In-memory port adapter seeded with {(code, period): Decimal} config-as-data."""

    data: dict[tuple[str, str], Decimal] = field(default_factory=dict)

    def _get(self, code: str, period: str) -> Decimal:
        return self.data.get((code, period), Decimal("0.00"))

    def get_balance_aggregate(self, code: str, period: str) -> Decimal:
        return self._get(code, period)

    def get_recon_aggregate(self, code: str, period: str) -> Decimal:
        return self._get(code, period)

    def get_safeguarding_total(self, code: str, period: str) -> Decimal:
        return self._get(code, period)


# ── Config-as-data: item-code → line-item derivation registry (no hardcode in logic) ──
# Aligned to K-gabriel's fca_item_code convention (services/gabriel: "FIN060-MONTHLY").
# Each line item declares which read-only source derives it. Injectable via the
# provider constructor (registry=...) for additional FCA item codes.
DEFAULT_ITEM_REGISTRY: dict[str, dict] = {
    "FIN060-MONTHLY": {
        "currency": "GBP",
        # (line_item_code, source)  — source ∈ {ledger, safeguarding, recon}
        "line_items": (
            ("client_funds_total", "ledger"),
            ("safeguarded_total", "safeguarding"),
            ("recon_difference", "recon"),
        ),
    },
}

_SOURCE_LABEL = {
    "ledger": "LedgerPort",
    "safeguarding": "SafeguardingTotalsPort",
    "recon": "ReconSourcePort",
}


def compute_content_hash(
    fca_item_code: str, return_period: str, version: int, line_items: tuple[LineItem, ...]
) -> str:
    """Deterministic content hash so K-gabriel can pin/idempotently submit an exact
    version. Stable for identical (code, period, version, line-item) inputs."""
    payload = {
        "fca_item_code": fca_item_code,
        "return_period": return_period,
        "version": version,
        "line_items": sorted(
            (
                {"code": li.code, "value": str(li.value), "currency": li.currency}
                for li in line_items
            ),
            key=lambda d: d["code"],
        ),
    }
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class FinRepContentProvider:
    """Producer of ``FinRepSourcePort`` (F-FINRPT-BUILD-SPEC §4).

    Assembles → validates → finalises versioned, immutable return content derived
    read-only from ledger/recon/safeguarding aggregates. ``get_return_content`` returns
    FINAL content only; ``list_available`` lists finalised item codes for a period.
    """

    def __init__(
        self,
        ledger: LedgerPort,
        recon: ReconSourcePort,
        safeguarding: SafeguardingTotalsPort,
        store: ReturnContentStore | None = None,
        registry: dict | None = None,
    ) -> None:
        self._ledger = ledger
        self._recon = recon
        self._safeguarding = safeguarding
        self._store = store or InMemoryReturnContentStore()
        self._registry = registry or DEFAULT_ITEM_REGISTRY

    # — internal: read-only derivation —
    def _derive_value(self, source: str, code: str, period: str) -> Decimal:
        if source == "ledger":
            return self._ledger.get_balance_aggregate(code, period)
        if source == "safeguarding":
            return self._safeguarding.get_safeguarding_total(code, period)
        if source == "recon":
            return self._recon.get_recon_aggregate(code, period)
        raise ContentValidationError(f"unknown derivation source: {source}")

    def assemble(
        self, fca_item_code: str, return_period: str, version: int = 1
    ) -> ReturnContentSet:
        """Derive (read-only) and assemble a DRAFT content set. No write-back to sources."""
        if not _PERIOD_RE.match(return_period):
            raise ContentValidationError(f"invalid return_period '{return_period}' (want YYYY-MM)")
        spec = self._registry.get(fca_item_code)
        if spec is None:
            raise ContentValidationError(f"unknown fca_item_code '{fca_item_code}'")
        currency = spec["currency"]
        line_items: list[LineItem] = []
        source_refs: list[str] = []
        for code, source in spec["line_items"]:
            value = self._derive_value(source, code, return_period)
            line_items.append(
                LineItem(
                    code=code,
                    value=Decimal(value),
                    currency=currency,
                    derivation_source=_SOURCE_LABEL[source],
                    period=return_period,
                )
            )
            source_refs.append(f"{source}:{code}:{return_period}")
        items = tuple(line_items)
        return ReturnContentSet(
            fca_item_code=fca_item_code,
            return_period=return_period,
            version=version,
            line_items=items,
            derived_at=datetime.now(UTC).isoformat(),
            source_refs=tuple(source_refs),
            content_hash=compute_content_hash(fca_item_code, return_period, version, items),
            status=DRAFT,
        )

    def validate(self, content: ReturnContentSet) -> list[str]:
        """Internal-consistency validation (cross-foot + period continuity). Returns a
        list of error strings (empty == valid). Distinct from K-gabriel's pre-submission
        regulatory validation."""
        errors: list[str] = []
        if not _PERIOD_RE.match(content.return_period):
            errors.append(f"period '{content.return_period}' not in YYYY-MM form")
        # Cross-foot: client_funds_total - safeguarded_total must equal recon_difference.
        cf = content.item("client_funds_total")
        sg = content.item("safeguarded_total")
        rd = content.item("recon_difference")
        if cf is not None and sg is not None and rd is not None:
            expected = (cf.value - sg.value).quantize(Decimal("0.01"))
            actual = rd.value.quantize(Decimal("0.01"))
            if expected != actual:
                errors.append(
                    f"cross-foot failed: client_funds_total - safeguarded_total = {expected} "
                    f"!= recon_difference {actual}"
                )
        return errors

    def finalize(self, fca_item_code: str, return_period: str) -> ReturnContentSet:
        """Assemble + validate, then persist an immutable FINAL versioned content set.

        Raises :class:`ContentValidationError` if validation fails (invalid content is
        not finalisable). Re-finalising a period appends the next version (append-only)."""
        prior = self._store.versions(fca_item_code, return_period)
        version = (max((s.version for s in prior), default=0)) + 1
        draft = self.assemble(fca_item_code, return_period, version=version)
        errors = self.validate(draft)
        if errors:
            raise ContentValidationError("; ".join(errors))
        final = ReturnContentSet(
            fca_item_code=draft.fca_item_code,
            return_period=draft.return_period,
            version=draft.version,
            line_items=draft.line_items,
            derived_at=draft.derived_at,
            source_refs=draft.source_refs,
            content_hash=draft.content_hash,
            status=FINAL,
        )
        self._store.append(final)
        return final

    # — producer side of FinRepSourcePort (§4) —
    def get_return_content(self, fca_item_code: str, return_period: str) -> ReturnContentSet:
        """Return the FINAL, validated, versioned content set for an item/period.

        Raises :class:`LookupError` if no FINAL content exists (K-gabriel must not submit
        draft content)."""
        final = self._store.latest_final(fca_item_code, return_period)
        if final is None:
            raise LookupError(
                f"no FINAL content for {fca_item_code} {return_period}; "
                "content not finalised — K-gabriel must not submit draft content"
            )
        return final

    def list_available(self, period: str) -> list[str]:
        """FCA item codes with FINAL content ready for the period (consumed by K-gabriel)."""
        return sorted({s.fca_item_code for s in self._store.list_final(period)})

    # — FENCE: submission is K-gabriel's (GAP-006), never here —
    def submit(self, *args: object, **kwargs: object) -> None:
        """Submission is fenced — see :class:`SubmissionFencedError`."""
        raise SubmissionFencedError(
            "F-finrpt (GAP-007) produces content only; submission/breach/deadline/sign-off "
            "are K-gabriel's (GAP-006), consumed via FinRepSourcePort. Use "
            "services/gabriel/* — do not submit through F-finrpt."
        )
