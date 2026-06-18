"""ADR-078 invariants: read-only contracts, Decimal (I-01), no mutate/trade/transfer ops."""

from decimal import Decimal

import pytest

from services.treasury.fx_exposure_port import (
    FXExposurePort,
    FXExposurePortError,
    InMemoryFXExposurePort,
)
from services.treasury.liquidity_forecast_port import (
    InMemoryLiquidityForecastPort,
    LiquidityForecastPort,
)
from services.treasury.nostro_recon_port import (
    InMemoryNOSTROReconPort,
    NOSTROReconPort,
    NOSTROReconPortError,
)

FORBIDDEN = ("execute", "trade", "transfer", "approve", "write", "mutate", "set_", "run_model")


@pytest.mark.parametrize("port_cls", [FXExposurePort, NOSTROReconPort, LiquidityForecastPort])
def test_no_mutating_methods_on_contract(port_cls):
    for name in dir(port_cls):
        assert not name.startswith(FORBIDDEN), f"forbidden op on {port_cls.__name__}: {name}"


def test_fx_exposure_reads_decimal():
    p = InMemoryFXExposurePort({"EUR": Decimal("100.50"), "USD": Decimal("-40.25")})
    assert p.get_exposure("EUR") == Decimal("100.50")
    assert p.get_total_exposure() == Decimal("140.75")
    assert isinstance(p.get_total_exposure(), Decimal)
    with pytest.raises(FXExposurePortError):
        p.get_exposure("GBP")


def test_nostro_reconcile_delta():
    p = InMemoryNOSTROReconPort({"N1": {"internal": Decimal("500"), "external": Decimal("450")}})
    assert p.reconcile("N1") == Decimal("50")
    with pytest.raises(NOSTROReconPortError):
        p.get_nostro_balances("N2")


def test_liquidity_forecast_reads():
    p = InMemoryLiquidityForecastPort({"inflow": Decimal("1000")}, Decimal("250"))
    assert p.get_forecast_inputs() == {"inflow": Decimal("1000")}
    assert p.get_current_position() == Decimal("250")
