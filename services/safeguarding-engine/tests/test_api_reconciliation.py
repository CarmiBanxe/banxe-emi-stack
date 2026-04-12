"""Tests for reconciliation API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_post_daily_reconcile(async_client: AsyncClient):
    """POST /api/v1/reconcile/daily."""
    response = await async_client.post("/api/v1/reconcile/daily")
    assert response.status_code in (200, 201)


@pytest.mark.asyncio
async def test_post_monthly_reconcile(async_client: AsyncClient):
    """POST /api/v1/reconcile/monthly."""
    response = await async_client.post("/api/v1/reconcile/monthly")
    assert response.status_code in (200, 201)


@pytest.mark.asyncio
async def test_get_reconcile_history(async_client: AsyncClient):
    """GET /api/v1/reconcile/history."""
    response = await async_client.get("/api/v1/reconcile/history")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_reconcile_detail(async_client: AsyncClient):
    """GET /api/v1/reconcile/{id}."""
    response = await async_client.get("/api/v1/reconcile/test-id")
    assert response.status_code in (200, 404)
