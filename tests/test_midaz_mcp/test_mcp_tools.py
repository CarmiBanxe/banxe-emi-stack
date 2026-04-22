"""Tests for Midaz MCP tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.mark.asyncio
class TestMidazMCPTools:
    async def test_midaz_create_org_returns_json(self):
        from banxe_mcp.server import midaz_create_org

        with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
            mock.return_value = {"org_id": "org_001", "name": "Banxe", "country": "GB"}
            result = await midaz_create_org("Banxe", "Banxe Ltd")
            data = json.loads(result)
            assert data["org_id"] == "org_001"

    async def test_midaz_create_org_http_error(self):
        from banxe_mcp.server import midaz_create_org

        with patch(
            "banxe_mcp.server._api_post",
            side_effect=httpx.HTTPStatusError(
                "400", request=MagicMock(), response=MagicMock(status_code=400)
            ),
        ):
            result = await midaz_create_org("Bad", "Bad Corp", "RU")
            assert "error" in json.loads(result)

    async def test_midaz_create_ledger_returns_json(self):
        from banxe_mcp.server import midaz_create_ledger

        with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
            mock.return_value = {
                "ledger_id": "ldg_001",
                "org_id": "org_001",
                "name": "Main",
            }
            result = await midaz_create_ledger("org_001", "Main")
            data = json.loads(result)
            assert "ledger_id" in data

    async def test_midaz_create_transaction_returns_json(self):
        from banxe_mcp.server import midaz_create_transaction

        entries = json.dumps([{"account_id": "acc_001", "amount": "100.00", "direction": "DEBIT"}])
        with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
            mock.return_value = {"transaction_id": "tx_001", "status": "POSTED"}
            result = await midaz_create_transaction("ldg_001", entries)
            data = json.loads(result)
            assert "transaction_id" in data

    async def test_midaz_get_balances_returns_json(self):
        from banxe_mcp.server import midaz_get_balances

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
            mock.return_value = {"account_id": "acc_001", "balances": []}
            result = await midaz_get_balances("acc_001")
            data = json.loads(result)
            assert "account_id" in data

    async def test_midaz_list_accounts_returns_json(self):
        from banxe_mcp.server import midaz_list_accounts

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
            mock.return_value = {"ledger_id": "ldg_001", "accounts": []}
            result = await midaz_list_accounts("ldg_001")
            data = json.loads(result)
            assert "ledger_id" in data

    async def test_midaz_create_transaction_invalid_json(self):
        from banxe_mcp.server import midaz_create_transaction

        result = await midaz_create_transaction("ldg_001", "not-valid-json{")
        data = json.loads(result)
        assert "error" in data

    async def test_midaz_create_ledger_http_error(self):
        from banxe_mcp.server import midaz_create_ledger

        with patch(
            "banxe_mcp.server._api_post",
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock(status_code=500)
            ),
        ):
            result = await midaz_create_ledger("org_001", "Ledger")
            assert "error" in json.loads(result)

    async def test_midaz_get_balances_http_error(self):
        from banxe_mcp.server import midaz_get_balances

        with patch(
            "banxe_mcp.server._api_get",
            side_effect=httpx.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock(status_code=404)
            ),
        ):
            result = await midaz_get_balances("acc_bad")
            assert "error" in json.loads(result)

    async def test_midaz_list_accounts_http_error(self):
        from banxe_mcp.server import midaz_list_accounts

        with patch(
            "banxe_mcp.server._api_get",
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock(status_code=500)
            ),
        ):
            result = await midaz_list_accounts("ldg_bad")
            assert "error" in json.loads(result)
