"""Tests for safeguarding API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_post_safeguard(async_client: AsyncClient):
    """POST /api/v1/safeguard - record safeguarding obligation."""
    response = await async_client.post(
        "/api/v1/safeguard",
        json={
            "amount": "10000.00",
            "currency": "GBP",
            "source": "e-money-receipt",
        },
    )
    assert response.status_code in (200, 201)


@pytest.mark.asyncio
async def test_get_positions(async_client: AsyncClient):
    """GET /api/v1/positions - current position summary."""
    response = await async_client.get("/api/v1/positions")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_positions_by_date(async_client: AsyncClient):
    """GET /api/v1/positions/{date} - historical position."""
    response = await async_client.get("/api/v1/positions/2025-01-01")
    assert response.status_code in (200, 404)


@pytest.mark.asyncio
async def test_get_shortfall(async_client: AsyncClient):
    """GET /api/v1/positions/shortfall."""
    response = await async_client.get("/api/v1/positions/shortfall")
    assert response.status_code == 200
