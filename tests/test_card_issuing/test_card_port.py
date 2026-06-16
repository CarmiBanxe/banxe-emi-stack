"""tests/test_card_issuing/test_card_port.py — CardPort CONTRACT scaffold tests.

ADR-053 C22 Cards mask / SPEC #15 Card issuance (CardPort + Paymentology).

Covers: module import safety, pure-ABC (cannot instantiate), abstractmethod
surface, enum stability, frozen value objects, I-01 Decimal invariant, the
error taxonomy, structural stub conformance, and — critically — the PCI-DSS
guarantee that NO full PAN / CVV / PIN field exists anywhere in the contract.
"""

from __future__ import annotations

import abc
import dataclasses
from decimal import Decimal
import importlib
import inspect

import pytest

from services.card_issuing.card_port import (
    CardLimits,
    CardLimitValidationError,
    CardNetwork,
    CardNotFound,
    CardPort,
    CardPortError,
    CardStatus,
    CardType,
    CardView,
    ComplianceBlock,
    DuplicateIssuance,
    InvalidCardState,
    IssueCardRequest,
    LimitChange,
    SpendPeriod,
)

# ---------------------------------------------------------------------------
# Expected allow-list (ADR-053 D4) — the mask scopes exactly these operations.
# ---------------------------------------------------------------------------

_ALLOW_LIST = frozenset(
    {
        "freeze",
        "block",
        "unfreeze",
        "read_card",
        "read_limits",
        "issue_card",
        "change_limit",
    }
)

# Forbidden cardholder-data tokens — PCI-DSS: none may appear as a contract field.
_FORBIDDEN_PAN_TOKENS = ("pan", "cvv", "cvc", "cvv2", "pin", "track", "magstripe")
# masked_pan / last_four are explicitly allowed display-safe fields.
_ALLOWED_PAN_FIELDS = frozenset({"masked_pan", "last_four"})


# ---------------------------------------------------------------------------
# Minimal in-memory stub — structural conformance only (NOT a real adapter)
# ---------------------------------------------------------------------------


class _CardPortStub(CardPort):
    """Concrete no-op stub proving the abstract surface is implementable."""

    _VIEW = CardView(
        card_id="card-001",
        status=CardStatus.ACTIVE,
        masked_pan="**** **** **** 1234",
        network=CardNetwork.MASTERCARD,
        card_type=CardType.VIRTUAL,
        last_four="1234",
        expiry_month=12,
        expiry_year=2030,
        name_on_card="A CARDHOLDER",
    )
    _LIMITS = CardLimits(
        card_id="card-001",
        period=SpendPeriod.DAILY,
        limit_amount=Decimal("1000.00"),
        currency="GBP",
    )

    async def freeze(self, card_id: str, actor: str, reason: str) -> CardView:
        return self._VIEW

    async def block(self, card_id: str, actor: str, reason: str) -> CardView:
        return self._VIEW

    async def unfreeze(self, card_id: str, actor: str) -> CardView:
        return self._VIEW

    async def read_card(self, card_id: str) -> CardView:
        return self._VIEW

    async def read_limits(self, card_id: str) -> CardLimits:
        return self._LIMITS

    async def issue_card(self, request: IssueCardRequest) -> CardView:
        return self._VIEW

    async def change_limit(self, card_id: str, new_limits: LimitChange) -> CardLimits:
        return self._LIMITS


# ---------------------------------------------------------------------------
# Import safety & ABC purity
# ---------------------------------------------------------------------------


def test_module_imports_without_side_effects() -> None:
    importlib.import_module("services.card_issuing.card_port")


def test_cardport_is_abstract_base_class() -> None:
    assert issubclass(CardPort, abc.ABC)
    assert inspect.isabstract(CardPort)


def test_cannot_instantiate_pure_abc() -> None:
    with pytest.raises(TypeError):
        CardPort()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Abstractmethod surface == ADR-053 D4 allow-list
# ---------------------------------------------------------------------------


def test_abstractmethods_match_allow_list() -> None:
    assert CardPort.__abstractmethods__ == _ALLOW_LIST


@pytest.mark.parametrize("op", sorted(_ALLOW_LIST))
def test_each_op_is_abstract_and_async(op: str) -> None:
    member = inspect.getattr_static(CardPort, op)
    assert getattr(member, "__isabstractmethod__", False), f"{op} must be abstract"
    assert inspect.iscoroutinefunction(member), f"{op} must be async"


def test_stub_implements_full_surface() -> None:
    # A concrete subclass implementing every abstractmethod is instantiable.
    assert isinstance(_CardPortStub(), CardPort)


# ---------------------------------------------------------------------------
# PCI-DSS: NO full PAN / CVV / PIN field anywhere in the contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dc", [CardView, CardLimits, IssueCardRequest, LimitChange])
def test_no_full_pan_cvv_pin_field_in_value_objects(dc: type) -> None:
    for f in dataclasses.fields(dc):
        if f.name in _ALLOWED_PAN_FIELDS:
            continue
        lowered = f.name.lower()
        for token in _FORBIDDEN_PAN_TOKENS:
            assert token not in lowered, f"{dc.__name__}.{f.name} leaks cardholder data ({token})"


def test_cardview_exposes_only_masked_pan() -> None:
    names = {f.name for f in dataclasses.fields(CardView)}
    assert "masked_pan" in names
    assert "pan" not in names
    assert "cvv" not in names
    assert "pin_hash" not in names


def test_no_pan_param_in_any_port_method() -> None:
    for op in _ALLOW_LIST:
        sig = inspect.signature(getattr(CardPort, op))
        for param in sig.parameters:
            lowered = param.lower()
            assert all(tok not in lowered for tok in _FORBIDDEN_PAN_TOKENS), (
                f"{op}({param}) leaks cardholder data"
            )


# ---------------------------------------------------------------------------
# Enum stability
# ---------------------------------------------------------------------------


def test_card_status_values() -> None:
    assert {s.value for s in CardStatus} == {
        "PENDING",
        "ACTIVE",
        "FROZEN",
        "BLOCKED",
        "EXPIRED",
        "REPLACED",
    }


def test_enum_str_values() -> None:
    assert CardNetwork.MASTERCARD == "MASTERCARD"
    assert CardType.VIRTUAL == "VIRTUAL"
    assert SpendPeriod.PER_TRANSACTION == "PER_TRANSACTION"


# ---------------------------------------------------------------------------
# Value objects: frozen + I-01 Decimal money invariant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dc", [CardView, CardLimits, IssueCardRequest, LimitChange])
def test_value_objects_are_frozen(dc: type) -> None:
    assert dataclasses.fields(dc) is not None
    params = dc.__dataclass_params__
    assert params.frozen is True


def test_card_view_is_immutable() -> None:
    view = _CardPortStub._VIEW
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.status = CardStatus.BLOCKED  # type: ignore[misc]


def test_money_fields_are_decimal() -> None:
    limits = CardLimits(
        card_id="c-1",
        period=SpendPeriod.MONTHLY,
        limit_amount=Decimal("250.50"),
        currency="EUR",
    )
    assert isinstance(limits.limit_amount, Decimal)
    change = LimitChange(
        period=SpendPeriod.DAILY,
        limit_amount=Decimal("99.99"),
        currency="EUR",
        actor="ops",
        correlation_id="corr-1",
    )
    assert isinstance(change.limit_amount, Decimal)


def test_list_fields_default_empty() -> None:
    limits = CardLimits(
        card_id="c-1",
        period=SpendPeriod.DAILY,
        limit_amount=Decimal("1"),
        currency="GBP",
    )
    assert limits.blocked_mccs == []
    assert limits.geo_restrictions == []


def test_issue_request_idempotency_key_optional() -> None:
    req = IssueCardRequest(
        entity_id="e-1",
        card_type=CardType.PHYSICAL,
        network=CardNetwork.VISA,
        currency="GBP",
        name_on_card="A B",
        actor="ops",
        correlation_id="corr-2",
    )
    assert req.client_card_id is None


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        CardNotFound,
        InvalidCardState,
        ComplianceBlock,
        CardLimitValidationError,
        DuplicateIssuance,
    ],
)
def test_errors_subclass_base_and_carry_correlation_id(exc: type[CardPortError]) -> None:
    assert issubclass(exc, CardPortError)
    err = exc("boom", correlation_id="corr-err")
    assert err.correlation_id == "corr-err"
    assert isinstance(err, Exception)


def test_base_error_requires_keyword_correlation_id() -> None:
    with pytest.raises(TypeError):
        CardPortError("boom")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Stub round-trip (exercises the async surface)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stub_async_surface_returns_contract_types() -> None:
    stub = _CardPortStub()
    assert isinstance(await stub.read_card("c-1"), CardView)
    assert isinstance(await stub.read_limits("c-1"), CardLimits)
    assert isinstance(await stub.freeze("c-1", "ops", "fraud"), CardView)
    assert isinstance(await stub.block("c-1", "ops", "lost"), CardView)
    assert isinstance(await stub.unfreeze("c-1", "ops"), CardView)
    req = IssueCardRequest(
        entity_id="e-1",
        card_type=CardType.VIRTUAL,
        network=CardNetwork.MASTERCARD,
        currency="GBP",
        name_on_card="A B",
        actor="ops",
        correlation_id="corr-3",
    )
    assert isinstance(await stub.issue_card(req), CardView)
    change = LimitChange(
        period=SpendPeriod.DAILY,
        limit_amount=Decimal("500"),
        currency="GBP",
        actor="ops",
        correlation_id="corr-4",
    )
    assert isinstance(await stub.change_limit("c-1", change), CardLimits)
