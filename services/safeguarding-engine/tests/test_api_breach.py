"""Tests for breach API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_post_breach(async_client: AsyncClient):
    """POST /api/v1/breaches - report a breach."""
    response = await async_client.post(
        "/api/v1/breaches",
        json={
            "breach_type": "shortfall",
            "severity": "critical",
            "description": "Test breach report",
        },
    )
    assert response.status_code in (200, 201)


@pytest.mark.asyncio
async def test_get_breaches(async_client: AsyncClient):
    """GET /api/v1/breaches - list all breaches."""
    response = await async_client.get("/api/v1/breaches")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_breach_detail(async_client: AsyncClient):
    """GET /api/v1/breaches/{id}."""
    response = await async_client.get("/api/v1/breaches/test-id")
    assert response.status_code in (200, 404)


@pytest.mark.asyncio
async def test_resolve_breach(async_client: AsyncClient):
    """PUT /api/v1/breaches/{id}/resolve."""
    response = await async_client.put(
        "/api/v1/breaches/test-id/resolve",
        json={
            "remediation_notes": "Resolved by transferring funds",
        },
    )
    assert response.status_code in (200, 404)
