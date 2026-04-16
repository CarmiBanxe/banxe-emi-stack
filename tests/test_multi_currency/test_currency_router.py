"""tests/test_multi_currency/test_currency_router.py — CurrencyRouter tests."""

from __future__ import annotations

import pytest

from services.multi_currency.currency_router import CurrencyRouter
from services.multi_currency.models import RoutingStrategy


def _make_router() -> CurrencyRouter:
    return CurrencyRouter()


# ── find_cheapest_path — direct ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_direct_pair_available_returns_two_hop() -> None:
    router = _make_router()
    path = await router.find_cheapest_path("GBP", "EUR", ["GBP/EUR", "EUR/USD"])
    assert path == ["GBP", "EUR"]


@pytest.mark.asyncio
async def test_direct_pair_reverse_direction_ok() -> None:
    router = _make_router()
    path = await router.find_cheapest_path("EUR", "GBP", ["GBP/EUR"])
    assert path == ["EUR", "GBP"]


@pytest.mark.asyncio
async def test_same_currency_returns_single_element() -> None:
    router = _make_router()
    path = await router.find_cheapest_path("GBP", "GBP", [])
    assert path == ["GBP"]


# ── find_cheapest_path — multi-hop ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_single_hop_via_hub_returns_three_elements() -> None:
    router = _make_router()
    # GBP→PLN not direct; GBP→EUR and EUR→PLN available
    path = await router.find_cheapest_path("GBP", "PLN", ["GBP/EUR", "EUR/PLN"])
    assert len(path) == 3
    assert path[0] == "GBP"
    assert path[2] == "PLN"


@pytest.mark.asyncio
async def test_path_via_eur_hub() -> None:
    router = _make_router()
    path = await router.find_cheapest_path("CHF", "PLN", ["CHF/EUR", "EUR/PLN"])
    assert "EUR" in path


@pytest.mark.asyncio
async def test_path_via_usd_hub() -> None:
    router = _make_router()
    path = await router.find_cheapest_path("GBP", "CHF", ["GBP/USD", "USD/CHF"])
    assert "USD" in path


# ── find_cheapest_path — no path ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_path_raises_value_error() -> None:
    router = _make_router()
    with pytest.raises(ValueError, match="No routing path found"):
        await router.find_cheapest_path("GBP", "HUF", [])


@pytest.mark.asyncio
async def test_no_path_disconnected_raises() -> None:
    router = _make_router()
    with pytest.raises(ValueError, match="No routing path found"):
        await router.find_cheapest_path("PLN", "CZK", ["GBP/EUR"])


# ── get_route_cost ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_route_cost_direct() -> None:
    router = _make_router()
    cost = await router.get_route_cost(["GBP", "EUR"], {"GBP/EUR": 10})
    assert cost == 10


@pytest.mark.asyncio
async def test_route_cost_two_hops() -> None:
    router = _make_router()
    cost = await router.get_route_cost(
        ["GBP", "EUR", "USD"],
        {"GBP/EUR": 10, "EUR/USD": 15},
    )
    assert cost == 25


@pytest.mark.asyncio
async def test_route_cost_reverse_key_lookup() -> None:
    router = _make_router()
    # path is GBP→EUR but spread stored as EUR/GBP
    cost = await router.get_route_cost(["GBP", "EUR"], {"EUR/GBP": 12})
    assert cost == 12


@pytest.mark.asyncio
async def test_route_cost_missing_spread_returns_zero() -> None:
    router = _make_router()
    cost = await router.get_route_cost(["GBP", "EUR"], {})
    assert cost == 0


# ── recommend_route ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recommend_route_cheapest_strategy() -> None:
    router = _make_router()
    result = await router.recommend_route("GBP", "EUR", RoutingStrategy.CHEAPEST)
    assert result["strategy"] == "CHEAPEST"
    assert "path" in result
    assert "estimated_spread_bps" in result


@pytest.mark.asyncio
async def test_recommend_route_fastest_strategy() -> None:
    router = _make_router()
    result = await router.recommend_route("GBP", "USD", RoutingStrategy.FASTEST)
    assert result["strategy"] == "FASTEST"
    assert isinstance(result["estimated_spread_bps"], int)


@pytest.mark.asyncio
async def test_recommend_route_direct_strategy() -> None:
    router = _make_router()
    result = await router.recommend_route("EUR", "CHF", RoutingStrategy.DIRECT)
    assert result["strategy"] == "DIRECT"


@pytest.mark.asyncio
async def test_recommend_route_path_contains_currencies() -> None:
    router = _make_router()
    result = await router.recommend_route("GBP", "EUR", RoutingStrategy.CHEAPEST)
    assert result["path"][0] == "GBP"
    assert result["path"][-1] == "EUR"
