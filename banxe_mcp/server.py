"""
banxe_mcp/server.py — BANXE EMI MCP Server (Phase 0: Read-Only Tools)
Model Context Protocol server exposing banking operations to AI agents.

MCP Strategy: agent-friendly EMI | FCA-compliant | PSD2-ready
Tools map 1:1 to existing FastAPI routers in api/routers/.

Phase 0 (this file): 7 read-only tools
Phase 1 (future): write ops + OAuth 2.0 scopes
Phase 2 (future): ecosystem play, Open Banking Tracker listing

Usage:
  python -m banxe_mcp                    # stdio mode (Claude Desktop)
  python -m banxe_mcp --transport sse   # SSE mode (web clients)

References: MCP-i-agentnoe-potreblenie-strategiia-dlia-BANXE-EMI-AI-Bank.md
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("banxe.mcp")

API_BASE = os.environ.get("BANXE_API_URL", "http://localhost:8000")
FX_BASE = os.environ.get("FRANKFURTER_URL", "http://localhost:8181")

mcp_server = FastMCP(
    "BANXE EMI AI Bank",
    instructions="FCA-authorised EMI platform — agentic banking via MCP. "
    "Exposes account, payment, KYC, AML, and FX tools for AI agents.",
)


async def _api_get(path: str) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
        r = await client.get(path)
        r.raise_for_status()
        return r.json()


async def _api_post(path: str, json_data: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=10.0) as client:
        r = await client.post(path, json=json_data)
        r.raise_for_status()
        return r.json()


async def _fx_get(path: str) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=FX_BASE, timeout=10.0) as client:
        r = await client.get(path)
        r.raise_for_status()
        return r.json()


# ── Tool 1: Account Balance ──────────────────────────────────────────────


@mcp_server.tool()
async def get_account_balance(account_id: str) -> str:
    """Get the current balance for a BANXE ledger account.

    Returns account balance with currency, available and pending amounts.
    FCA CASS 7.15: real-time balance, never cached >60s.

    Args:
        account_id: The ledger account ID (e.g. 'acc-operational-001')
    """
    try:
        data = await _api_get(f"/v1/ledger/accounts/{account_id}/balance")
        return (
            f"Account: {data.get('account_id', account_id)}\n"
            f"Balance: {data.get('balance', 'N/A')} {data.get('currency', '')}\n"
            f"Available: {data.get('available', 'N/A')}\n"
            f"Pending: {data.get('pending', '0')}\n"
            f"As of: {data.get('as_of', datetime.now(UTC).isoformat())}"
        )
    except httpx.HTTPStatusError as e:
        return f"Error fetching balance for {account_id}: {e.response.status_code}"
    except httpx.ConnectError:
        return "Error: BANXE API unavailable. Ensure uvicorn is running on :8000"


# ── Tool 2: List Accounts ────────────────────────────────────────────────


@mcp_server.tool()
async def list_accounts() -> str:
    """List all BANXE ledger accounts.

    Returns operational, safeguarding, and client accounts
    with their types and currencies.
    """
    try:
        data = await _api_get("/v1/ledger/accounts")
        accounts = data.get("accounts", [])
        if not accounts:
            return "No accounts found."
        lines = [f"BANXE Accounts ({len(accounts)} total):"]
        for acc in accounts:
            lines.append(
                f"  {acc.get('account_id', '?')} | "
                f"{acc.get('account_type', '?')} | "
                f"{acc.get('currency', '?')} | "
                f"{acc.get('display_name', '')}"
            )
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error listing accounts: {e.response.status_code}"
    except httpx.ConnectError:
        return "Error: BANXE API unavailable."


# ── Tool 3: Transaction History ──────────────────────────────────────────


@mcp_server.tool()
async def get_transaction_history(account_id: str, period: str = "current") -> str:
    """Get transaction history / statement for a BANXE account.

    Returns transactions for the specified period.

    Args:
        account_id: The ledger account ID
        period: Statement period - 'current', '2025-01', etc.
    """
    try:
        data = await _api_get(f"/v1/statements/{account_id}?period={period}")
        txns = data.get("transactions", [])
        lines = [
            f"Statement for {account_id} (period: {data.get('period', period)})",
            f"Opening: {data.get('opening_balance', 'N/A')} | "
            f"Closing: {data.get('closing_balance', 'N/A')}",
            f"Transactions: {len(txns)}",
            "---",
        ]
        for tx in txns[:20]:
            lines.append(
                f"  {tx.get('date', '?')} | {tx.get('amount', '?')} | "
                f"{tx.get('description', '?')} | {tx.get('status', '?')}"
            )
        if len(txns) > 20:
            lines.append(f"  ... and {len(txns) - 20} more")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error fetching statement: {e.response.status_code}"
    except httpx.ConnectError:
        return "Error: BANXE API unavailable."


# ── Tool 4: KYC Status ──────────────────────────────────────────────────


@mcp_server.tool()
async def get_kyc_status(customer_id: str) -> str:
    """Check KYC verification status for a BANXE customer.

    Returns the current KYC workflow state, verification level,
    and any pending document requirements.

    Args:
        customer_id: The customer ID to check KYC for
    """
    try:
        data = await _api_get(f"/v1/kyc/{customer_id}")
        return (
            f"Customer: {customer_id}\n"
            f"KYC Status: {data.get('status', 'UNKNOWN')}\n"
            f"Verification Level: {data.get('verification_level', 'N/A')}\n"
            f"Risk Rating: {data.get('risk_rating', 'N/A')}\n"
            f"Documents: {data.get('documents_status', 'N/A')}\n"
            f"Last Updated: {data.get('updated_at', 'N/A')}"
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"No KYC record found for customer {customer_id}"
        return f"Error checking KYC: {e.response.status_code}"
    except httpx.ConnectError:
        return "Error: BANXE API unavailable."


# ── Tool 5: AML Alert Check ─────────────────────────────────────────────


@mcp_server.tool()
async def check_aml_alert(transaction_id: str) -> str:
    """Check AML/fraud alerts for a specific transaction.

    Runs the transaction through the fraud+AML pipeline and returns
    risk assessment, alerts, and recommended actions.

    Args:
        transaction_id: The transaction ID to check
    """
    try:
        data = await _api_post(
            "/v1/fraud/assess",
            {
                "transaction_id": transaction_id,
                "amount": "0",
                "currency": "GBP",
                "customer_id": "check-only",
            },
        )
        return (
            f"Transaction: {transaction_id}\n"
            f"Fraud Score: {data.get('fraud_score', 'N/A')}\n"
            f"AML Decision: {data.get('aml_decision', 'N/A')}\n"
            f"Risk Level: {data.get('risk_level', 'N/A')}\n"
            f"Alerts: {data.get('alerts', [])}\n"
            f"Action: {data.get('recommended_action', 'NONE')}"
        )
    except httpx.HTTPStatusError as e:
        return f"Error checking AML for {transaction_id}: {e.response.status_code}"
    except httpx.ConnectError:
        return "Error: BANXE API unavailable."


# ── Tool 6: Exchange Rate ────────────────────────────────────────────────


@mcp_server.tool()
async def get_exchange_rate(from_currency: str, to_currency: str) -> str:
    """Get current ECB exchange rate between two currencies.

    Powered by Frankfurter (self-hosted ECB rates, no API key needed).
    Updated daily by the European Central Bank.

    Args:
        from_currency: Source currency code (e.g. 'EUR', 'GBP', 'USD')
        to_currency: Target currency code (e.g. 'USD', 'EUR', 'GBP')
    """
    try:
        data = await _fx_get(f"/latest?from={from_currency.upper()}&to={to_currency.upper()}")
        rate = data.get("rates", {}).get(to_currency.upper(), "N/A")
        return (
            f"Exchange Rate ({data.get('date', 'today')}):\n"
            f"1 {from_currency.upper()} = {rate} {to_currency.upper()}\n"
            f"Source: European Central Bank (via Frankfurter)"
        )
    except httpx.HTTPStatusError as e:
        return f"Error fetching rate {from_currency}/{to_currency}: {e.response.status_code}"
    except httpx.ConnectError:
        return "Error: Frankfurter service unavailable on :8181"


# ── Tool 7: Payment Status ──────────────────────────────────────────────


@mcp_server.tool()
async def get_payment_status(payment_id: str) -> str:
    """Get the status of a BANXE payment by its ID.

    Returns payment details including rail, amount, status and timestamps.

    Args:
        payment_id: The payment/idempotency key
    """
    try:
        data = await _api_get(f"/v1/payments/{payment_id}")
        return (
            f"Payment: {data.get('payment_id', payment_id)}\n"
            f"Status: {data.get('status', 'UNKNOWN')}\n"
            f"Amount: {data.get('amount', 'N/A')} {data.get('currency', '')}\n"
            f"Rail: {data.get('rail', 'N/A')}\n"
            f"Provider ID: {data.get('provider_payment_id', 'N/A')}\n"
            f"Created: {data.get('created_at', 'N/A')}"
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Payment {payment_id} not found"
        return f"Error fetching payment: {e.response.status_code}"
    except httpx.ConnectError:
        return "Error: BANXE API unavailable."


# ── Resources ────────────────────────────────────────────────────────────


@mcp_server.resource("banxe://health")
async def health_resource() -> str:
    """BANXE API health status."""
    try:
        data = await _api_get("/health")
        return f"API Status: {data.get('status', 'unknown')} | Version: {data.get('version', '?')}"
    except Exception:
        return "API Status: UNAVAILABLE"


@mcp_server.resource("banxe://info")
async def info_resource() -> str:
    """BANXE EMI platform information."""
    return (
        "BANXE AI Bank — FCA-authorised EMI Platform\n"
        "MCP Server v0.1.0 (Phase 0: Read-Only)\n"
        "Tools: get_account_balance, list_accounts, get_transaction_history, "
        "get_kyc_status, check_aml_alert, get_exchange_rate, get_payment_status\n"
        "FCA basis: CASS 7.15, MLR 2017, PSR 2017\n"
        "Trust zone: RED"
    )


# ── Entry point ──────────────────────────────────────────────────────────


def main() -> None:
    """Run MCP server."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    transport = "stdio"
    if "--transport" in sys.argv:
        idx = sys.argv.index("--transport")
        if idx + 1 < len(sys.argv):
            transport = sys.argv[idx + 1]
    logger.info("Starting BANXE MCP Server (transport=%s)", transport)
    mcp_server.run(transport=transport)


if __name__ == "__main__":
    main()
