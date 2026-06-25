"""F-finrpt (GAP-007) content-core tests — FIN-RPT return content producer.

Covers the F-FINRPT-BUILD-SPEC §6 DoD: Decimal-only, read-only derivation,
validation rules, immutability/versioning, stable content_hash, FINAL-only producer
contract, and the submission fence (no GAP-006 logic here). Real assertions, no padding.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from services.reporting.finrep_content_core import (
    DEFAULT_ITEM_REGISTRY,
    FINAL,
    ContentValidationError,
    FinRepContentProvider,
    InMemoryReturnContentStore,
    LineItem,
    ReturnContentSet,
    SubmissionFencedError,
    _DictSource,
    compute_content_hash,
)

ITEM = "FIN060-MONTHLY"
PERIOD = "2026-05"


def _consistent_sources() -> _DictSource:
    # client_funds_total - safeguarded_total == recon_difference (cross-foot holds)
    return _DictSource(
        data={
            ("client_funds_total", PERIOD): Decimal("1000000.00"),
            ("safeguarded_total", PERIOD): Decimal("950000.00"),
            ("recon_difference", PERIOD): Decimal("50000.00"),
        }
    )


def _provider(src: _DictSource | None = None) -> tuple[FinRepContentProvider, _DictSource]:
    src = src or _consistent_sources()
    provider = FinRepContentProvider(ledger=src, recon=src, safeguarding=src)
    return provider, src


# ── §6: Decimal-only (I-01) ─────────────────────────────────────────────────────
def test_return_content_decimal_only():
    with pytest.raises(TypeError):
        LineItem(code="x", value=1.5, currency="GBP", derivation_source="LedgerPort", period=PERIOD)
    provider, _ = _provider()
    content = provider.finalize(ITEM, PERIOD)
    assert all(isinstance(li.value, Decimal) for li in content.line_items)


# ── §6: derived read-only from ledger + recon + safeguarding ────────────────────
def test_content_derived_from_ledger_and_recon():
    provider, src = _provider()
    before = dict(src.data)
    content = provider.assemble(ITEM, PERIOD)
    assert content.item("client_funds_total").value == Decimal("1000000.00")
    assert content.item("recon_difference").value == Decimal("50000.00")
    assert content.item("client_funds_total").derivation_source == "LedgerPort"
    assert content.item("recon_difference").derivation_source == "ReconSourcePort"
    assert any("recon:" in r for r in content.source_refs)
    # read-only: derivation never wrote back to the source aggregates
    assert src.data == before


# ── §6: validation rules (cross-foot + period continuity) ───────────────────────
def test_content_validation_rules():
    provider, _ = _provider()
    assert provider.validate(provider.assemble(ITEM, PERIOD)) == []
    # cross-foot break → invalid, not finalisable
    bad = _DictSource(
        data={
            ("client_funds_total", PERIOD): Decimal("1000000.00"),
            ("safeguarded_total", PERIOD): Decimal("950000.00"),
            ("recon_difference", PERIOD): Decimal("40000.00"),  # should be 50000
        }
    )
    bad_provider, _ = _provider(bad)
    errs = bad_provider.validate(bad_provider.assemble(ITEM, PERIOD))
    assert errs and "cross-foot" in errs[0]
    with pytest.raises(ContentValidationError):
        bad_provider.finalize(ITEM, PERIOD)
    # bad period rejected at assembly
    with pytest.raises(ContentValidationError):
        provider.assemble(ITEM, "2026-13")
    with pytest.raises(ContentValidationError):
        provider.assemble("UNKNOWN-CODE", PERIOD)


# ── §6: immutable after FINAL + versioning ──────────────────────────────────────
def test_content_immutable_after_final():
    provider, _ = _provider()
    final = provider.finalize(ITEM, PERIOD)
    assert final.status == FINAL
    with pytest.raises(dataclasses.FrozenInstanceError):
        final.version = 99  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        final.line_items[0].value = Decimal("1")  # type: ignore[misc]
    # store is append-only (no update/delete); re-finalise appends the next version
    second = provider.finalize(ITEM, PERIOD)
    assert second.version == 2
    assert not hasattr(provider._store, "update")
    assert not hasattr(provider._store, "delete")


# ── §6: content_hash stable per version ─────────────────────────────────────────
def test_content_hash_stable_per_version():
    provider, _ = _provider()
    final = provider.finalize(ITEM, PERIOD)
    recomputed = compute_content_hash(ITEM, PERIOD, final.version, final.line_items)
    assert final.content_hash == recomputed
    # identical inputs in a fresh provider → identical hash for the same version
    provider2, _ = _provider()
    final2 = provider2.finalize(ITEM, PERIOD)
    assert final2.content_hash == final.content_hash
    # different version → different hash (pinnable)
    v2 = provider.finalize(ITEM, PERIOD)
    assert v2.content_hash != final.content_hash


# ── §6: FinRepSourcePort returns FINAL only ─────────────────────────────────────
def test_finrep_source_port_returns_final_only():
    provider, _ = _provider()
    with pytest.raises(LookupError):
        provider.get_return_content(ITEM, PERIOD)  # nothing finalised yet
    assert provider.list_available(PERIOD) == []
    provider.finalize(ITEM, PERIOD)
    got = provider.get_return_content(ITEM, PERIOD)
    assert got.status == FINAL and got.fca_item_code == ITEM
    assert provider.list_available(PERIOD) == [ITEM]


# ── §6: no submission logic present (fence to K-gabriel GAP-006) ─────────────────
def test_no_submission_logic_present():
    provider, _ = _provider()
    with pytest.raises(SubmissionFencedError):
        provider.submit(ITEM, PERIOD)
    # the content-core must not import or reimplement any submission/transport client
    import services.reporting.finrep_content_core as core

    src = __import__("inspect").getsource(core)
    for forbidden in (
        "RegDataClient",
        "fca_regdata_client",
        "returns_governor",
        "httpx",
        "requests",
    ):
        assert forbidden not in src, (
            f"submission/transport reference leaked into content-core: {forbidden}"
        )


# ── defensive validation branches ──────────────────────────────────────────────
def test_unknown_derivation_source_rejected():
    bad_registry = {"BAD-ITEM": {"currency": "GBP", "line_items": (("x", "nonexistent_source"),)}}
    provider, _ = _provider()
    provider._registry = bad_registry
    with pytest.raises(ContentValidationError):
        provider.assemble("BAD-ITEM", PERIOD)


def test_validate_flags_malformed_period_on_constructed_set():
    provider, _ = _provider()
    hand_built = ReturnContentSet(
        fca_item_code=ITEM,
        return_period="2026-99",  # malformed
        version=1,
        line_items=(),
        derived_at="2026-05-01T00:00:00+00:00",
        source_refs=(),
        content_hash="x",
        status="DRAFT",
    )
    errs = provider.validate(hand_built)
    assert any("YYYY-MM" in e for e in errs)


# ── store + registry sanity ─────────────────────────────────────────────────────
def test_store_and_registry_shape():
    store = InMemoryReturnContentStore()
    assert store.latest_final(ITEM, PERIOD) is None
    assert store.list_final(PERIOD) == []
    assert "FIN060-MONTHLY" in DEFAULT_ITEM_REGISTRY
    provider, _ = _provider(InMemoryReturnContentStore() and _consistent_sources())
    provider.finalize(ITEM, PERIOD)
    assert isinstance(provider.get_return_content(ITEM, PERIOD), ReturnContentSet)
