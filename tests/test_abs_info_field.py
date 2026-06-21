"""MIG genuine-gap #1 — advisory ABS info-field metadata (descriptive, no live/Midaz/KYC).

characterization: AbsInfoFieldPort / AbsInfoFieldDescriptor / AbsFieldType shape; deterministic.
contract: descriptors carry exactly {field_key,label,field_type,group,source}; fail-closed get_field.
fence: module imports no midaz/ledger/kyc; no float; no monetary numerics.
"""

from dataclasses import fields
from pathlib import Path

from services.abs.info_field import (
    AbsFieldType,
    AbsInfoFieldDescriptor,
    AbsInfoFieldPort,
    SandboxAbsInfoFieldProvider,
)


def _provider() -> SandboxAbsInfoFieldProvider:
    return SandboxAbsInfoFieldProvider()


def test_port_and_descriptor_shape() -> None:
    assert issubclass(SandboxAbsInfoFieldProvider, AbsInfoFieldPort)
    names = {f.name for f in fields(AbsInfoFieldDescriptor)}
    assert names == {"field_key", "label", "field_type", "group", "source"}
    assert {t.value for t in AbsFieldType} == {"string", "number", "boolean", "date", "enum"}


def test_list_fields_descriptive() -> None:
    out = _provider().list_fields()
    assert len(out) == 5
    assert all(isinstance(d, AbsInfoFieldDescriptor) for d in out)
    assert all(d.source == "sandbox-mock" for d in out)
    assert all(isinstance(d.field_type, AbsFieldType) for d in out)


def test_get_field_fail_closed() -> None:
    p = _provider()
    assert p.get_field("customer_ref") is not None
    assert p.get_field("customer_ref").group == "customer"
    assert p.get_field("nope") is None  # fail-closed


def test_deterministic() -> None:
    assert _provider().list_fields() == _provider().list_fields()


def test_fence_no_midaz_ledger_kyc_no_float() -> None:
    import services.abs.info_field as mod

    text = Path(mod.__file__).read_text()
    import_lines = "\n".join(
        ln for ln in text.splitlines() if ln.strip().startswith(("import ", "from "))
    ).lower()
    for bad in ("midaz", "ledger", "kyc", "kyb", "sumsub", "httpx", "requests"):
        assert bad not in import_lines, f"forbidden import token: {bad}"
    # no float USAGE: descriptive metadata only (docstring may mention the word "float")
    assert "float(" not in text and ": float" not in text and "-> float" not in text
