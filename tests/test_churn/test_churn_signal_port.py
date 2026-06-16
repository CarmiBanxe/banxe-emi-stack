"""ChurnSignalPort contract test suite — 100% coverage over
services/churn/churn_signal_port.py.

Validates the READ-ONLY contract and the InMemoryChurnSignalPort double:
get_at_risk_customers (threshold filter + highest-risk-first ordering + range guard),
get_churn_signals (known / unknown → CustomerNotFound), the fail_on_call provider-error
path, the value types (Decimal numerics, opaque handles), the error hierarchy, and the
read-only INVARIANT (the port exposes NO mutate / trigger / retention / write method).

asyncio_mode = "auto" (pyproject.toml): every ``async def test_*`` is auto-collected.
"""

from __future__ import annotations

from decimal import Decimal
import inspect

import pytest

from services.churn.churn_signal_port import (
    AtRiskCustomer,
    ChurnSignal,
    ChurnSignalCode,
    ChurnSignalPort,
    ChurnSignalPortError,
    ChurnSignalSet,
    CustomerNotFound,
    InMemoryChurnSignalPort,
    RiskBand,
)

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _signal_set(
    customer_id: str,
    *,
    cohort: str = "retail-eu",
    risk: str = "0.50",
    band: RiskBand = RiskBand.ELEVATED,
) -> ChurnSignalSet:
    return ChurnSignalSet(
        customer_id=customer_id,
        cohort=cohort,
        risk_score=Decimal(risk),
        band=band,
        signals=(ChurnSignal(code=ChurnSignalCode.DORMANCY, weight=Decimal("0.40"), detail="d"),),
    )


# ---------------------------------------------------------------------------
# 1. get_at_risk_customers — threshold filter + ordering
# ---------------------------------------------------------------------------


async def test_at_risk_filters_by_threshold_and_orders_high_first() -> None:
    port = InMemoryChurnSignalPort(
        signals={
            "a": _signal_set("a", risk="0.90", band=RiskBand.HIGH),
            "b": _signal_set("b", risk="0.50"),
            "c": _signal_set("c", risk="0.10", band=RiskBand.LOW),
        }
    )
    result = await port.get_at_risk_customers(Decimal("0.40"))

    assert [c.customer_id for c in result] == ["a", "b"]  # c (0.10) excluded; ordered desc
    assert all(isinstance(c, AtRiskCustomer) for c in result)
    assert result[0].risk_score == Decimal("0.90")
    assert result[0].band is RiskBand.HIGH
    assert result[0].cohort == "retail-eu"


async def test_at_risk_threshold_zero_returns_all() -> None:
    port = InMemoryChurnSignalPort()  # default seed: 2 customers
    result = await port.get_at_risk_customers(Decimal("0"))
    assert len(result) == 2


async def test_at_risk_high_threshold_returns_empty() -> None:
    port = InMemoryChurnSignalPort()
    result = await port.get_at_risk_customers(Decimal("1"))
    assert result == []


@pytest.mark.parametrize("bad", [Decimal("-0.01"), Decimal("1.01")])
async def test_at_risk_threshold_out_of_range_raises(bad: Decimal) -> None:
    port = InMemoryChurnSignalPort()
    with pytest.raises(ChurnSignalPortError, match="threshold out of range"):
        await port.get_at_risk_customers(bad)


# ---------------------------------------------------------------------------
# 2. get_churn_signals — known / unknown
# ---------------------------------------------------------------------------


async def test_get_churn_signals_known_returns_set() -> None:
    port = InMemoryChurnSignalPort(signals={"cust-x": _signal_set("cust-x", risk="0.77")})
    out = await port.get_churn_signals("cust-x")
    assert isinstance(out, ChurnSignalSet)
    assert out.customer_id == "cust-x"
    assert out.risk_score == Decimal("0.77")
    assert out.signals[0].code is ChurnSignalCode.DORMANCY


async def test_get_churn_signals_unknown_raises_customer_not_found() -> None:
    port = InMemoryChurnSignalPort(signals={})
    with pytest.raises(CustomerNotFound, match="Unknown customer"):
        await port.get_churn_signals("nope")


async def test_default_seed_has_expected_customers() -> None:
    port = InMemoryChurnSignalPort()
    out = await port.get_churn_signals("cust-1001")
    assert out.band is RiskBand.HIGH
    assert out.risk_score == Decimal("0.82")
    assert len(out.signals) == 2


# ---------------------------------------------------------------------------
# 3. fail_on_call — provider-error path on every read
# ---------------------------------------------------------------------------


async def test_fail_on_call_raises_on_at_risk() -> None:
    port = InMemoryChurnSignalPort(fail_on_call=True)
    with pytest.raises(ChurnSignalPortError, match="configured to fail"):
        await port.get_at_risk_customers(Decimal("0.50"))


async def test_fail_on_call_raises_on_get_signals() -> None:
    port = InMemoryChurnSignalPort(fail_on_call=True)
    with pytest.raises(ChurnSignalPortError, match="configured to fail"):
        await port.get_churn_signals("cust-1001")


# ---------------------------------------------------------------------------
# 4. Value types / enums (I-01 Decimal, opaque handles)
# ---------------------------------------------------------------------------


def test_value_types_are_decimal_and_opaque() -> None:
    sig = ChurnSignal(code=ChurnSignalCode.SUSPENSION, weight=Decimal("0.5"))
    assert sig.detail == ""  # default
    arc = AtRiskCustomer(
        customer_id="c1", cohort="coh", risk_score=Decimal("0.6"), band=RiskBand.ELEVATED
    )
    assert isinstance(arc.risk_score, Decimal)
    cs = ChurnSignalSet(
        customer_id="c1", cohort="coh", risk_score=Decimal("0.6"), band=RiskBand.ELEVATED
    )
    assert cs.signals == ()  # default empty


def test_enum_values() -> None:
    assert RiskBand.LOW.value == "LOW"
    assert RiskBand.ELEVATED.value == "ELEVATED"
    assert RiskBand.HIGH.value == "HIGH"
    assert ChurnSignalCode.DORMANCY.value == "DORMANCY"
    assert ChurnSignalCode.SUSPENSION.value == "SUSPENSION"
    assert ChurnSignalCode.INACTIVITY.value == "INACTIVITY"
    assert ChurnSignalCode.REACTIVATION_LAPSE.value == "REACTIVATION_LAPSE"


def test_error_hierarchy() -> None:
    assert issubclass(CustomerNotFound, ChurnSignalPortError)
    assert issubclass(ChurnSignalPortError, Exception)


# ---------------------------------------------------------------------------
# 5. INVARIANT: the port is READ-ONLY — no mutate/trigger/retention/write method
# ---------------------------------------------------------------------------


def test_port_is_read_only_no_mutating_methods() -> None:
    """ChurnSignalPort exposes ONLY the two reads — no retention/trigger/write/mutate op.

    This is the contract-level enforcement of the agent's read-only invariant: a mutating
    op cannot be reached because no such method exists on the port at all.
    """
    public = {
        n
        for n, _ in inspect.getmembers(ChurnSignalPort, inspect.isfunction)
        if not n.startswith("_")
    }
    assert public == {"get_at_risk_customers", "get_churn_signals"}
    forbidden = ("trigger", "retention", "write", "update", "mutate", "suspend", "close", "set_")
    for name in public:
        assert not any(tok in name.lower() for tok in forbidden), name


def test_abstract_port_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        ChurnSignalPort()  # type: ignore[abstract]
