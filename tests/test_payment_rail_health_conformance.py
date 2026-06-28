"""FROZEN PaymentRailPort.health() conformance for the wired general rails (ADR-102).

Both wired rails (selected by PAYMENT_ADAPTER) must satisfy PaymentRailPort.health(), and the
new health() delegate must mirror the existing health_check() return value (no duplicated logic).
No live network calls.
"""

from __future__ import annotations

import pytest

from services.payment.mock_payment_adapter import MockPaymentAdapter
from services.payment.modulr_client import ModulrPaymentAdapter

#: Methods declared by the FROZEN PaymentRailPort Protocol (payment_port.py).
_PORT_METHODS = ("submit_payment", "get_payment_status", "health")


@pytest.mark.parametrize("adapter", [MockPaymentAdapter(), ModulrPaymentAdapter()])
def test_wired_rail_satisfies_payment_rail_port(adapter: object) -> None:
    """Each wired rail structurally satisfies the FROZEN PaymentRailPort (incl. health()).

    PaymentRailPort is a non-runtime_checkable Protocol (frozen — not modified here), so this
    asserts the required methods structurally rather than via isinstance.
    """
    for method in _PORT_METHODS:
        assert callable(getattr(adapter, method, None)), f"missing PaymentRailPort.{method}"


def test_mock_health_mirrors_health_check() -> None:
    adapter = MockPaymentAdapter()
    assert adapter.health() is adapter.health_check() is True


def test_modulr_health_mirrors_health_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """health() returns exactly what health_check() returns (no separate network logic)."""
    adapter = ModulrPaymentAdapter()
    # health_check pings the API; stub it so the test makes no live call.
    monkeypatch.setattr(adapter, "health_check", lambda: False)
    assert adapter.health() is False
    monkeypatch.setattr(adapter, "health_check", lambda: True)
    assert adapter.health() is True
