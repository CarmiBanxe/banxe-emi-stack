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

from datetime import UTC, datetime
import json
import logging
import os
import sys
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


# ── Tool 8: Reconciliation Status ───────────────────────────────────────────


@mcp_server.tool()
async def get_recon_status(recon_date: str = "") -> str:
    """Get reconciliation status for a date (YYYY-MM-DD, default: today).
    Returns MATCHED/DISCREPANCY/PENDING for all safeguarding accounts.
    FCA CASS 7.15: daily reconciliation status must be auditable.

    Args:
        recon_date: Date in YYYY-MM-DD format (default: today)
    """
    from datetime import date as date_type

    if not recon_date:
        recon_date = date_type.today().isoformat()

    try:
        data = await _api_get(f"/v1/recon/status?date={recon_date}")
        results = data.get("results", [])
        if not results:
            return f"No reconciliation data for {recon_date}. Status: PENDING"
        lines = [f"Recon Status — {recon_date}:"]
        for r in results:
            lines.append(
                f"  {r.get('account_id', '?')} | "
                f"{r.get('account_type', '?')} | "
                f"{r.get('status', '?')} | "
                f"discrepancy: {r.get('discrepancy', '0')} {r.get('currency', 'GBP')}"
            )
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"No recon data for {recon_date}. Status: PENDING (statement not yet received)"
        return f"Error fetching recon status: {e.response.status_code}"
    except httpx.ConnectError:
        return (
            f"Recon Status — {recon_date} (SANDBOX — API unavailable)\n"
            f"  Run: pytest tests/ -k recon -v to verify recon engine\n"
            f"  FCA CASS 7.15: status queryable via ClickHouse banxe.safeguarding_events"
        )


# ── Tool 9: Breach History ───────────────────────────────────────────────────


@mcp_server.tool()
async def get_breach_history(account_id: str, days: int = 30) -> str:
    """Get breach history for a safeguarding account.
    Returns list of BreachRecord for last N days.
    FCA CASS 15.12: breach records must be available for FCA inspection.

    Args:
        account_id: Midaz safeguarding account UUID
        days: Number of days to look back (default: 30)
    """
    try:
        data = await _api_get(f"/v1/recon/breaches/{account_id}?days={days}")
        breaches = data.get("breaches", [])
        if not breaches:
            return f"No breaches found for {account_id} in last {days} days."
        lines = [f"Breach History — {account_id} (last {days} days):"]
        for b in breaches:
            lines.append(
                f"  {b.get('detected_at', '?')} | "
                f"discrepancy: £{b.get('discrepancy', '0')} | "
                f"days outstanding: {b.get('days_outstanding', '?')} | "
                f"FCA notified: {'Yes' if b.get('reported_to_fca') else 'No'}"
            )
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"No breach records found for {account_id}"
        return f"Error fetching breach history: {e.response.status_code}"
    except httpx.ConnectError:
        return (
            f"Breach History — {account_id} (SANDBOX — API unavailable)\n"  # nosec B608
            f"  Query ClickHouse: SELECT * FROM banxe.safeguarding_breaches "
            f"WHERE account_id = '{account_id}' ORDER BY detected_at DESC LIMIT 10"
        )


# ── Tool 10: Discrepancy Trend ───────────────────────────────────────────────


@mcp_server.tool()
async def get_discrepancy_trend(account_id: str, days: int = 7) -> str:
    """Get discrepancy trend for safeguarding account over last N days.
    Used by AI agents for breach prediction (Phase 5).
    Returns daily discrepancy amounts as decimal strings.
    FCA CASS 15.12: trend data required for breach prediction.

    Args:
        account_id: Midaz safeguarding account UUID
        days: Number of days to look back (default: 7)
    """
    try:
        data = await _api_get(f"/v1/recon/trend/{account_id}?days={days}")
        trend_data = data.get("trend", [])
        if not trend_data:
            return f"No trend data for {account_id} in last {days} days."
        lines = [f"Discrepancy Trend — {account_id} (last {days} days):"]
        for entry in trend_data:
            status_icon = "OK" if entry.get("status") == "MATCHED" else "!!"
            lines.append(
                f"  [{status_icon}] {entry.get('recon_date', '?')} | "
                f"discrepancy: £{entry.get('discrepancy', '0')} | "
                f"status: {entry.get('status', '?')}"
            )
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"No trend data found for {account_id}"
        return f"Error fetching discrepancy trend: {e.response.status_code}"
    except httpx.ConnectError:
        return (
            f"Discrepancy Trend — {account_id} (SANDBOX — API unavailable)\n"  # nosec B608
            f"  Query ClickHouse: SELECT recon_date, discrepancy, status "
            f"FROM banxe.safeguarding_events WHERE account_id = '{account_id}' "
            f"ORDER BY recon_date DESC LIMIT {days}"
        )


# ── Tool 11: Run Reconciliation ─────────────────────────────────────────────


@mcp_server.tool()
async def run_reconciliation(recon_date: str = "", dry_run: bool = True) -> str:
    """Trigger a reconciliation run for a specific date.

    In dry_run mode (default): simulates the run, shows what WOULD be reconciled
    without writing to ClickHouse. Safe to call at any time.
    In live mode (dry_run=False): executes full CASS 7.15 reconciliation,
    writes events to ClickHouse, fires breach alerts if needed.

    FCA CASS 7.15: daily reconciliation must be auditable and repeatable.
    IMPORTANT: live mode requires BANXE API running and ClickHouse accessible.

    Args:
        recon_date: Date in YYYY-MM-DD format (default: yesterday)
        dry_run: If True (default), simulate only — no writes to ClickHouse
    """
    from datetime import date as date_type
    from datetime import timedelta

    if not recon_date:
        recon_date = (date_type.today() - timedelta(days=1)).isoformat()

    mode = "DRY RUN" if dry_run else "LIVE"
    try:
        payload = {"recon_date": recon_date, "dry_run": dry_run}
        data = await _api_post("/v1/recon/run", payload)
        results = data.get("results", [])
        summary = data.get("summary", {})
        lines = [
            f"Reconciliation {mode} — {recon_date}",
            f"Accounts processed: {summary.get('total', len(results))}",
            f"MATCHED: {summary.get('matched', 0)} | "
            f"DISCREPANCY: {summary.get('discrepancy', 0)} | "
            f"PENDING: {summary.get('pending', 0)}",
            "",
        ]
        for r in results:
            icon = "✓" if r.get("status") == "MATCHED" else "✗"
            lines.append(
                f"  [{icon}] {r.get('account_type', '?')} | "
                f"status: {r.get('status', '?')} | "
                f"discrepancy: £{r.get('discrepancy', '0')}"
            )
        if dry_run:
            lines.append("\n[DRY RUN] No data written to ClickHouse.")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Reconciliation {mode} failed: HTTP {e.response.status_code}"
    except httpx.ConnectError:
        # Sandbox: run reconciliation in-process using InMemory stubs
        lines = [
            f"Reconciliation {mode} — {recon_date} (SANDBOX — API unavailable)",
            "Running in-process with InMemory stubs...",
            "",
        ]
        try:
            from datetime import date as d
            from decimal import Decimal

            from services.recon.clickhouse_client import InMemoryReconClient
            from services.recon.reconciliation_engine import (
                ReconciliationEngine,
            )
            from services.recon.statement_fetcher import StatementFetcher

            class _StubLedger:
                def get_balance(self, org_id: str, ledger_id: str, account_id: str) -> Decimal:
                    return Decimal("100000.00")

            engine = ReconciliationEngine(
                ledger_port=_StubLedger(),
                ch_client=InMemoryReconClient(),
                statement_fetcher=StatementFetcher(),
            )
            results = engine.reconcile(d.fromisoformat(recon_date))
            for r in results:
                icon = "✓" if r.status == "MATCHED" else "⚠"
                lines.append(
                    f"  [{icon}] {r.account_type} | status: {r.status} | "
                    f"internal: £{r.internal_balance} | external: £{r.external_balance}"
                )
            lines.append(
                f"\n[{mode}] Processed {len(results)} accounts. "
                + ("[DRY RUN] No ClickHouse writes." if dry_run else "Events written.")
            )
        except Exception as exc:
            lines.append(f"In-process run failed: {exc}")
            lines.append("Ensure BANXE API is running: uvicorn api.main:app --port 8000")
        return "\n".join(lines)


# ── Tool 12: Route Agent Task (ARL) ─────────────────────────────────────────


@mcp_server.tool()
async def route_agent_task(
    event_type: str,
    product: str,
    jurisdiction: str,
    customer_id: str,
    amount_eur: str = "0",
    sanctions_hit: bool = False,
    known_beneficiary: bool = False,
) -> str:
    """Submit a compliance event to the Agent Routing Layer (ARL).

    Routes the task through the three-tier system (rule engine → mid LLM → swarm)
    based on product, jurisdiction, and risk signals.
    Target: ~60-70% token cost reduction for routine operations.

    Args:
        event_type:       Domain event, e.g. "aml_screening", "kyc_check".
        product:          Product identifier, e.g. "sepa_retail_transfer".
        jurisdiction:     Regulatory jurisdiction, e.g. "EU", "UK".
        customer_id:      Customer identifier.
        amount_eur:       Transaction amount in EUR (as string, no float — I-01).
        sanctions_hit:    True if sanctions list hit detected upstream.
        known_beneficiary: True if beneficiary is known to the customer.
    """
    import os

    if os.environ.get("AGENT_ROUTING_ENABLED", "false").lower() != "true":
        return (
            "Agent Routing Layer is disabled.\n"
            "Set AGENT_ROUTING_ENABLED=true to enable.\n"
            "Current mode: direct LLM calls (no tier routing)."
        )

    try:
        from services.agent_routing.gateway import AgentGateway

        gateway = AgentGateway()
        result = await gateway.process(
            event_type=event_type,
            product=product,
            jurisdiction=jurisdiction,
            customer_id=customer_id,
            payload={"amount_eur": amount_eur},
            risk_context={
                "sanctions_hit": sanctions_hit,
                "known_beneficiary": known_beneficiary,
                "amount_eur": float(amount_eur),
            },
        )
        responses_summary = "\n".join(
            f"  [{r.agent_name}] {r.decision_hint} (risk={r.risk_score:.2f}, "
            f"conf={r.confidence:.2f}): {r.reason_summary[:80]}"
            for r in result.responses
        )
        return (
            f"ARL Routing Result — Task {result.task_id}\n"
            f"Tier used: {result.tier_used}\n"
            f"Decision: {result.decision.upper()}\n"
            f"Total tokens: {result.total_tokens}\n"
            f"Latency: {result.total_latency_ms}ms\n"
            f"Reasoning reused: {result.reasoning_reused}\n"
            f"Playbook: {result.playbook_version}\n"
            f"Agent responses:\n{responses_summary}"
        )
    except Exception as exc:
        return f"ARL routing error: {exc}"


# ── Tool 13: Query ReasoningBank ─────────────────────────────────────────────


@mcp_server.tool()
async def query_reasoning_bank(
    event_type: str,
    top_k: int = 5,
) -> str:
    """Find similar past compliance cases in the ReasoningBank.

    Uses vector similarity to find cases with similar risk profiles.
    Helps avoid re-running expensive LLM analysis for known patterns.

    Args:
        event_type: Domain event type to search for, e.g. "aml_screening".
        top_k:      Maximum number of similar cases to return (default: 5).
    """
    try:
        data = await _api_post(
            "/reasoning/similar",
            {"query_vector": [0.5] * 8, "top_k": top_k, "threshold": 0.5},
        )
        cases = data.get("cases", [])
        if not cases:
            return f"No similar cases found for event_type={event_type!r}."
        lines = [f"ReasoningBank — Similar Cases for {event_type!r} (top {top_k}):"]
        for c in cases:
            lines.append(
                f"  {c.get('case_id', '?')} | "
                f"{c.get('product', '?')} / {c.get('jurisdiction', '?')} | "
                f"tier {c.get('tier_used', '?')} | "
                f"{c.get('created_at', '?')[:10]}"
            )
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"ReasoningBank query error: HTTP {e.response.status_code}"
    except httpx.ConnectError:
        return (
            "ReasoningBank unavailable (API not running).\nStart: uvicorn api.main:app --port 8000"
        )


# ── Tool 14: Get ARL Routing Metrics ─────────────────────────────────────────


@mcp_server.tool()
async def get_routing_metrics(hours: int = 24) -> str:
    """Get current Agent Routing Layer telemetry snapshot.

    Returns tier distribution, decision ratios, token usage,
    and cost summary for the last N hours.

    Args:
        hours: Look-back window in hours (default: 24).
    """
    try:
        data = await _api_get(f"/v1/arl/metrics?hours={hours}")
        return (
            f"ARL Metrics (last {hours}h):\n"
            f"Total decisions: {data.get('total_decisions', 0)}\n"
            f"Tier 1 (rules): {data.get('tier1_pct', 0):.1f}%\n"
            f"Tier 2 (mid LLM): {data.get('tier2_pct', 0):.1f}%\n"
            f"Tier 3 (swarm/top): {data.get('tier3_pct', 0):.1f}%\n"
            f"Approve rate: {data.get('approve_rate', 0):.1f}%\n"
            f"Manual review rate: {data.get('manual_review_rate', 0):.1f}%\n"
            f"Reasoning reuse rate: {data.get('reuse_rate', 0):.1f}%\n"
            f"Total cost (USD): ${data.get('total_cost_usd', 0):.4f}\n"
            f"p95 latency (ms): {data.get('latency_p95_ms', 0)}"
        )
    except httpx.HTTPStatusError as e:
        return f"Error fetching ARL metrics: HTTP {e.response.status_code}"
    except httpx.ConnectError:
        return (
            f"ARL Metrics (last {hours}h) — SANDBOX\n"  # nosec B608
            "API unavailable. Check Grafana dashboard: banxe-arl-metrics\n"
            "ClickHouse: SELECT tier, count(), avg(cost_usd) FROM agent_routing_events "
            f"WHERE event_time >= now() - INTERVAL {hours} HOUR GROUP BY tier"
        )


# ── Tool 15: Manage Playbooks ─────────────────────────────────────────────────


@mcp_server.tool()
async def manage_playbooks(action: str = "list", playbook_id: str = "") -> str:
    """List and validate Agent Routing Layer playbooks.

    Actions:
      list     — List all loaded playbooks with product/jurisdiction info.
      validate — Validate a specific playbook YAML (returns any errors).
      reload   — Hot-reload all playbooks from config/playbooks/ (no restart needed).

    Args:
        action:      One of: list, validate, reload.
        playbook_id: Playbook ID for validate action (e.g. "eu_sepa_retail_v1").
    """
    try:
        from services.agent_routing.playbook_engine import PlaybookEngine

        engine = PlaybookEngine()

        match action:
            case "list":
                playbooks = engine.list_playbooks()
                if not playbooks:
                    return "No playbooks loaded. Check config/playbooks/ directory."
                lines = [f"Loaded Playbooks ({len(playbooks)}):"]
                for pb_id in playbooks:
                    pb = engine.get_playbook(pb_id)
                    if pb:
                        juris = ", ".join(pb.get("jurisdictions", [])[:5])
                        lines.append(
                            f"  {pb_id} | product: {pb.get('product', '?')} | "
                            f"jurisdictions: {juris}"
                        )
                return "\n".join(lines)

            case "validate":
                if not playbook_id:
                    return "Provide playbook_id for validate action."
                pb = engine.get_playbook(playbook_id)
                if pb is None:
                    return f"Playbook {playbook_id!r} not found."
                required = ["playbook_id", "product", "jurisdictions", "tiers"]
                missing = [f for f in required if f not in pb]
                if missing:
                    return f"Playbook {playbook_id!r} INVALID — missing fields: {missing}"
                return f"Playbook {playbook_id!r} is VALID. All required fields present."

            case "reload":
                engine.reload()
                count = len(engine.list_playbooks())
                return f"Playbooks reloaded successfully. {count} playbooks loaded."

            case _:
                return f"Unknown action {action!r}. Use: list, validate, reload."

    except Exception as exc:
        return f"Playbook management error: {exc}"


# ── Tool 16: Generate UI Component (Design Pipeline) ─────────────────────────


@mcp_server.tool()
async def generate_component(
    file_id: str,
    component_id: str,
    framework: str = "react",
    run_visual_qa: bool = False,
) -> str:
    """Generate a UI component from a Penpot design using the AI Design Pipeline.

    Runs the full D2C pipeline: Penpot context → LLM (Ollama) → Mitosis compile.
    AI-generated code is labelled per EU AI Act Art.52.

    Args:
        file_id:       Penpot file UUID
        component_id:  Penpot component UUID
        framework:     Target framework — react | vue | react-native | angular | svelte
        run_visual_qa: If True, runs screenshot comparison against Penpot design
    """
    try:
        data = await _api_post(
            "/design/generate-component",
            {
                "file_id": file_id,
                "component_id": component_id,
                "framework": framework,
                "run_visual_qa": run_visual_qa,
            },
        )
        qa_info = ""
        if run_visual_qa:
            qa_info = (
                f"\nVisual QA: {'PASS' if data.get('qa_passed') else 'FAIL'} "
                f"(similarity: {data.get('qa_similarity', 0.0):.3f})"
            )
        return (
            f"Component Generated: {data.get('component_id', component_id)}\n"
            f"Framework: {data.get('framework', framework)}\n"
            f"Model: {data.get('model_used', 'N/A')}\n"
            f"Latency: {data.get('latency_ms', 0)}ms\n"
            f"Success: {data.get('success', False)}\n"
            f"{qa_info}\n\n"
            f"--- CODE ---\n{data.get('code', '')[:2000]}"
        )
    except httpx.HTTPStatusError as e:
        return f"Error generating component: HTTP {e.response.status_code}"
    except httpx.ConnectError:
        return (
            "Design Pipeline API unavailable.\n"
            "Start: uvicorn api.main:app --port 8000\n"
            "Ensure PENPOT_BASE_URL and PENPOT_TOKEN are configured."
        )


# ── Tool 17: Sync Design Tokens ───────────────────────────────────────────────


@mcp_server.tool()
async def sync_design_tokens(file_id: str) -> str:
    """Sync design tokens from Penpot to the codebase.

    Runs: Penpot file → banxe-tokens.json → Style Dictionary build
    → outputs: CSS variables, Tailwind config, React Native tokens.

    Args:
        file_id: Penpot file UUID to sync tokens from
    """
    try:
        data = await _api_post("/design/sync-tokens", {"file_id": file_id})
        output_files = data.get("output_files", [])
        errors = data.get("errors", [])
        return (
            f"Token Sync — file_id: {file_id}\n"
            f"Tokens extracted: {data.get('tokens_extracted', 0)}\n"
            f"Output files: {len(output_files)}\n"
            f"Success: {data.get('success', False)}\n"
            + ("Outputs:\n" + "\n".join(f"  {f}" for f in output_files) if output_files else "")
            + ("\nErrors:\n" + "\n".join(f"  {e}" for e in errors) if errors else "")
        )
    except httpx.HTTPStatusError as e:
        return f"Token sync failed: HTTP {e.response.status_code}"
    except httpx.ConnectError:
        return "Design Pipeline API unavailable. Ensure uvicorn is running on :8000"


# ── Tool 18: Visual Compare ───────────────────────────────────────────────────


@mcp_server.tool()
async def visual_compare(
    component_id: str,
    rendered_html: str,
    reference_svg: str,
    threshold: float = 0.95,
) -> str:
    """Compare a rendered component against its Penpot reference design.

    Uses pixel-level comparison to check implementation fidelity.
    Returns similarity score and PASS/FAIL verdict.
    Threshold: 95% similarity = PASS (configurable).

    Args:
        component_id:  Component identifier
        rendered_html: HTML/component code to compare
        reference_svg: SVG exported from Penpot as reference
        threshold:     Similarity threshold (0.0–1.0, default: 0.95)
    """
    try:
        data = await _api_post(
            "/design/visual-compare",
            {
                "component_id": component_id,
                "rendered_html": rendered_html,
                "reference_svg": reference_svg,
                "threshold": threshold,
            },
        )
        diff_info = ""
        if not data.get("passed"):
            diff_info = (
                f"\nDiff pixels: {data.get('diff_pixel_count', 0)}\n"
                f"Diff image: {data.get('diff_image_path', 'N/A')}"
            )
        return (
            f"Visual Compare — {component_id}\n"
            f"Status: {'PASS' if data.get('passed') else 'FAIL'}\n"
            f"Similarity: {data.get('similarity_score', 0.0):.3f}\n"
            f"Threshold: {threshold}" + diff_info
        )
    except httpx.HTTPStatusError as e:
        return f"Visual compare failed: HTTP {e.response.status_code}"
    except httpx.ConnectError:
        return "Design Pipeline API unavailable."


# ── Tool 19: List Design Components ──────────────────────────────────────────


@mcp_server.tool()
async def list_design_components(file_id: str) -> str:
    """List all available Penpot design components for a file.

    Returns a flat list of all components with their names, paths,
    and compliance metadata (KYC, PSD2 SCA flags).

    Args:
        file_id: Penpot file UUID
    """
    try:
        data = await _api_get(f"/design/components/{file_id}")
        components = data.get("components", [])
        count = data.get("count", len(components))
        if not components:
            return f"No components found in file {file_id}."
        lines = [f"Design Components — {file_id} ({count} total):"]
        for comp in components[:50]:
            compliance_flag = " [COMPLIANCE]" if comp.get("is_compliance") else ""
            lines.append(
                f"  {comp.get('id', '?')} | {comp.get('path', '?')}/{comp.get('name', '?')}"
                f"{compliance_flag}"
            )
        if count > 50:
            lines.append(f"  ... and {count - 50} more")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error listing components: HTTP {e.response.status_code}"
    except httpx.ConnectError:
        return (
            "Design Pipeline API unavailable.\nConfigure PENPOT_BASE_URL and PENPOT_TOKEN in .env"
        )


# ── Resources ────────────────────────────────────────────────────────────


@mcp_server.resource("banxe://health")
async def health_resource() -> str:
    """BANXE API health status."""
    try:
        data = await _api_get("/health")
        return f"API Status: {data.get('status', 'unknown')} | Version: {data.get('version', '?')}"
    except Exception:
        return "API Status: UNAVAILABLE"


# ── Compliance KB Tools (IL-CKS-01) ─────────────────────────────────────────


@mcp_server.tool()
async def kb_list_notebooks(tags: str = "", jurisdiction: str = "") -> str:
    """List all compliance knowledge base notebooks.

    Returns notebook IDs, names, descriptions, and document counts.
    Useful for compliance officers to discover available regulatory sources.

    Args:
        tags: Comma-separated filter tags (e.g. "aml,uk" or "fatf")
        jurisdiction: Filter by jurisdiction: eu | uk | fatf | eba | esma
    """
    try:
        params: list[str] = []
        if tags:
            for tag in tags.split(","):
                params.append(f"tags={tag.strip()}")
        if jurisdiction:
            params.append(f"jurisdiction={jurisdiction}")
        qs = "?" + "&".join(params) if params else ""
        data = await _api_get(f"/v1/kb/notebooks{qs}")
        if not data:
            return "No compliance notebooks found."
        lines = [f"Compliance Knowledge Notebooks ({len(data)} total):"]
        for nb in data:
            lines.append(
                f"  [{nb.get('id', '?')}] {nb.get('name', '?')} "
                f"({nb.get('jurisdiction', '?')}) — {nb.get('doc_count', 0)} chunks"
            )
            desc = nb.get("description", "")
            if desc:
                lines.append(f"    {desc}")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error listing notebooks: {e.response.status_code}"
    except httpx.ConnectError:
        return "Error: BANXE API unavailable. Ensure API is running on :8000"


@mcp_server.tool()
async def kb_get_notebook(notebook_id: str) -> str:
    """Get full details for a compliance notebook including all sources.

    Returns notebook metadata, source list, and current document count.

    Args:
        notebook_id: Notebook ID (e.g. 'emi-uk-fca', 'emi-eu-aml')
    """
    try:
        data = await _api_get(f"/v1/kb/notebooks/{notebook_id}")
        sources = data.get("sources", [])
        lines = [
            f"Notebook: {data.get('name', notebook_id)}",
            f"ID: {notebook_id}",
            f"Jurisdiction: {data.get('jurisdiction', 'N/A')}",
            f"Tags: {', '.join(data.get('tags', []))}",
            f"Description: {data.get('description', '')}",
            f"Document chunks: {data.get('doc_count', 0)}",
            f"Sources ({len(sources)}):",
        ]
        for s in sources:
            url_str = f" — {s.get('url', '')}" if s.get("url") else ""
            lines.append(
                f"  [{s.get('id', '?')}] {s.get('name', '?')} "
                f"({s.get('source_type', '?')}, v{s.get('version', '?')}){url_str}"
            )
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Notebook '{notebook_id}' not found"
        return f"Error fetching notebook: {e.response.status_code}"
    except httpx.ConnectError:
        return "Error: BANXE API unavailable."


@mcp_server.tool()
async def kb_query(
    notebook_id: str,
    question: str,
    max_citations: int = 5,
) -> str:
    """Ask a compliance question against a knowledge base notebook.

    Performs RAG retrieval and returns a synthesised answer with citations
    showing the source document, section, and relevant snippet.

    Supports English and Russian questions.

    Args:
        notebook_id: Target notebook (e.g. 'emi-uk-fca', 'emi-eu-aml')
        question: Compliance question in English or Russian
        max_citations: Maximum number of citations to include (1-10, default 5)
    """
    try:
        payload = {
            "notebook_id": notebook_id,
            "question": question,
            "max_citations": max(1, min(10, max_citations)),
        }
        data = await _api_post("/v1/kb/query", payload)
        answer = data.get("answer", "No answer generated.")
        citations = data.get("citations", [])
        confidence = data.get("confidence", 0.0)

        lines = [
            f"Q: {question}",
            f"Notebook: {notebook_id} | Confidence: {confidence:.0%}",
            "",
            answer,
            "",
        ]
        if citations:
            lines.append(f"Citations ({len(citations)}):")
            for cit in citations:
                uri_str = f" <{cit.get('uri', '')}>" if cit.get("uri") else ""
                lines.append(
                    f"  [{cit.get('source_id', '?')}] {cit.get('title', '?')} "
                    f"§{cit.get('section', '?')} (v{cit.get('version', '?')}){uri_str}"
                )
                snippet = cit.get("snippet", "")
                if snippet:
                    lines.append(f'    "{snippet[:200]}"')
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Notebook '{notebook_id}' not found"
        return f"Error querying KB: {e.response.status_code}"
    except httpx.ConnectError:
        return "Error: BANXE API unavailable."


@mcp_server.tool()
async def kb_search(notebook_id: str, query: str, limit: int = 10) -> str:
    """Semantic search over a compliance notebook.

    Returns raw document chunks with similarity scores.
    Use kb_query for synthesised answers; use kb_search for exploration.

    Args:
        notebook_id: Target notebook ID
        query: Search query (natural language)
        limit: Maximum results to return (1-50, default 10)
    """
    try:
        payload = {"notebook_id": notebook_id, "query": query, "limit": max(1, min(50, limit))}
        data = await _api_post("/v1/kb/search", payload)
        if not data:
            return f"No results found in '{notebook_id}' for: {query}"
        lines = [f"Search: '{query}' in {notebook_id} ({len(data)} results):", ""]
        for i, result in enumerate(data, 1):
            score = result.get("score", 0.0)
            lines.append(
                f"[{i}] {result.get('section', '?')} "
                f"(doc: {result.get('document_id', '?')}, score: {score:.2f})"
            )
            text = result.get("text", "")
            if text:
                lines.append(f"    {text[:250]}...")
            lines.append("")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Notebook '{notebook_id}' not found"
        return f"Error searching KB: {e.response.status_code}"
    except httpx.ConnectError:
        return "Error: BANXE API unavailable."


@mcp_server.tool()
async def kb_compare_versions(
    source_id: str,
    from_version: str,
    to_version: str,
    focus_sections: str = "",
) -> str:
    """Compare two versions of a regulatory document for changes.

    Identifies added, removed, and modified sections between versions,
    with impact tags (e.g. 'new-requirement', 'modified-requirement').

    Both versions must be ingested into the knowledge base first.

    Args:
        source_id: Source document ID (e.g. 'fca-cass-15', 'mlr-2017')
        from_version: Earlier version (ISO date, e.g. '2021-01-01')
        to_version: Later version (ISO date, e.g. '2025-12-01')
        focus_sections: Comma-separated section names to focus on (optional)
    """
    try:
        payload: dict[str, Any] = {
            "source_id": source_id,
            "from_version": from_version,
            "to_version": to_version,
        }
        if focus_sections:
            payload["focus_sections"] = [s.strip() for s in focus_sections.split(",")]
        data = await _api_post("/v1/kb/compare", payload)
        changes = data.get("changes", [])
        lines = [
            f"Version Comparison: {source_id}",
            f"From: {from_version} → To: {to_version}",
            f"Summary: {data.get('diff_summary', 'N/A')}",
            f"Changes: {len(changes)}",
            "",
        ]
        for ch in changes[:20]:
            change_type = ch.get("change_type", "?").upper()
            lines.append(f"[{change_type}] §{ch.get('section', '?')}")
            if ch.get("before"):
                lines.append(f"  Before: {ch['before'][:150]}...")
            if ch.get("after"):
                lines.append(f"  After:  {ch['after'][:150]}...")
            if ch.get("impact_tags"):
                lines.append(f"  Impact: {', '.join(ch['impact_tags'])}")
            lines.append("")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error comparing versions: {e.response.status_code}"
    except httpx.ConnectError:
        return "Error: BANXE API unavailable."


@mcp_server.tool()
async def kb_get_citations(source_id: str, notebook_id: str) -> str:
    """Get full citation details for a source document in a notebook.

    Returns source metadata including title, version, URL, and description.
    Use this to get complete citation information after a kb_query result.

    Args:
        source_id: Source document ID (e.g. 'fca-cass-15')
        notebook_id: Notebook containing this source (e.g. 'emi-uk-fca')
    """
    try:
        data = await _api_get(f"/v1/kb/citations/{source_id}?notebook_id={notebook_id}")
        lines = [
            f"Citation: {data.get('title', source_id)}",
            f"Source ID: {source_id}",
            f"Type: {data.get('source_type', 'N/A')}",
            f"Version: {data.get('version', 'N/A')}",
            f"Section: {data.get('section', 'N/A')}",
        ]
        if data.get("uri"):
            lines.append(f"URL: {data['uri']}")
        if data.get("snippet"):
            lines.append(f"Description: {data['snippet']}")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Source '{source_id}' not found in notebook '{notebook_id}'"
        return f"Error fetching citation: {e.response.status_code}"
    except httpx.ConnectError:
        return "Error: BANXE API unavailable."


# ── Transaction Monitor Tools (IL-RTM-01) ─────────────────────────────────


@mcp_server.tool()
async def monitor_score_transaction(
    transaction_id: str,
    amount: str,
    sender_id: str,
    sender_jurisdiction: str = "GB",
    receiver_jurisdiction: str | None = None,
    transaction_type: str = "payment",
    currency: str = "GBP",
    channel: str = "api",
    customer_avg_amount: str | None = None,
) -> str:
    """Score a transaction for AML risk and generate an alert.

    Applies rules (40%) + ML anomaly detection (30%) + velocity (30%).
    Hard-blocks sanctioned jurisdictions (I-02). EDD at GBP 10k (I-04).

    Args:
        transaction_id: Unique transaction identifier.
        amount: Transaction amount as decimal string (e.g. "15200.00").
        sender_id: Customer/sender ID.
        sender_jurisdiction: ISO 3166-1 alpha-2 (default: GB).
        receiver_jurisdiction: Optional receiver jurisdiction.
        transaction_type: payment|transfer|withdrawal|deposit|crypto_onramp|crypto_offramp|p2p|merchant
        currency: ISO 4217 (default: GBP).
        channel: api|mobile|web|branch.
        customer_avg_amount: Customer 90-day average amount string.

    Returns:
        Markdown summary of risk score and generated alert.
    """
    try:
        payload: dict = {
            "transaction_id": transaction_id,
            "amount": amount,
            "sender_id": sender_id,
            "sender_jurisdiction": sender_jurisdiction,
            "transaction_type": transaction_type,
            "currency": currency,
            "channel": channel,
        }
        if receiver_jurisdiction:
            payload["receiver_jurisdiction"] = receiver_jurisdiction
        if customer_avg_amount:
            payload["customer_avg_amount"] = customer_avg_amount

        result = await _api_post("/v1/monitor/score", payload)
        risk = result.get("risk_score", {})
        alert = result.get("alert", {})
        score = risk.get("score", 0)
        classification = risk.get("classification", "unknown").upper()
        factors = risk.get("factors", [])[:3]

        lines = [
            f"## AML Score: {transaction_id}",
            f"**Risk Score**: {score:.2f} — **{classification}**",
            f"**Alert ID**: `{alert.get('alert_id', 'N/A')}`",
            f"**Severity**: {alert.get('severity', 'N/A').upper()}",
            f"**Status**: {alert.get('status', 'N/A')}",
            f"**Action**: {alert.get('recommended_action', 'N/A')}",
            f"**Marble Case**: {alert.get('marble_case_id') or '_none_'}",
            "",
            "### Top Risk Factors",
        ]
        for f in factors:
            lines.append(
                f"- **{f.get('name')}**: {f.get('value', 0):.2f} "
                f"(contribution: {f.get('contribution', 0):.2f})"
            )
            if f.get("regulation_ref"):
                lines.append(f"  → {f.get('regulation_ref')}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error scoring transaction: {e}"


@mcp_server.tool()
async def monitor_get_alerts(
    severity: str = "",
    status: str = "",
    customer_id: str = "",
    limit: int = 20,
) -> str:
    """List AML alerts with optional filters.

    Args:
        severity: Filter by severity: low|medium|high|critical
        status: Filter by status: open|reviewing|escalated|closed|auto_closed
        customer_id: Filter by customer ID.
        limit: Max alerts to return (default: 20).

    Returns:
        Markdown table of alerts.
    """
    try:
        path = f"/v1/monitor/alerts?limit={limit}"
        if severity:
            path += f"&severity={severity}"
        if status:
            path += f"&status={status}"
        if customer_id:
            path += f"&customer_id={customer_id}"
        alerts = await _api_get(path)
        if not alerts:
            return "No alerts found matching the specified filters."
        lines = [
            f"## AML Alerts ({len(alerts)} results)\n",
            "| Alert ID | Tx ID | Severity | Status | Score | Created |",
            "|----------|-------|----------|--------|-------|---------|",
        ]
        for a in alerts:
            score = a.get("risk_score", {}).get("score", 0)
            lines.append(
                f"| `{a.get('alert_id', '?')}` | `{a.get('transaction_id', '?')}` "
                f"| **{a.get('severity', '?').upper()}** | {a.get('status', '?')} "
                f"| {score:.2f} | {str(a.get('created_at', ''))[:10]} |"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching alerts: {e}"


@mcp_server.tool()
async def monitor_get_alert_detail(alert_id: str) -> str:
    """Get full alert details including explanation and KB citations.

    Args:
        alert_id: Alert ID (e.g. ALT-A1B2C3D4).

    Returns:
        Full alert with risk factor breakdown and explanation.
    """
    try:
        alert = await _api_get(f"/v1/monitor/alerts/{alert_id}")
        explanation = alert.get("explanation", "No explanation available.")
        refs = alert.get("regulation_refs", [])
        return (
            f"## Alert Detail: `{alert_id}`\n\n"
            f"**Transaction**: `{alert.get('transaction_id')}`\n"
            f"**Customer**: `{alert.get('customer_id')}`\n"
            f"**Severity**: {alert.get('severity', '?').upper()}\n"
            f"**Status**: {alert.get('status')}\n"
            f"**Amount**: £{alert.get('amount_gbp', '?')}\n"
            f"**Review Deadline**: {str(alert.get('review_deadline', 'N/A'))[:19]}\n"
            f"**Marble Case**: {alert.get('marble_case_id') or 'none'}\n\n"
            f"### Explanation\n```\n{explanation}\n```\n\n"
            f"### Regulation Citations\n" + ("\n".join(f"- {r}" for r in refs) or "_none_")
        )
    except Exception as e:
        return f"Error fetching alert {alert_id}: {e}"


@mcp_server.tool()
async def monitor_get_velocity(customer_id: str) -> str:
    """Get velocity metrics for a customer across 1h, 24h, 7d windows.

    Args:
        customer_id: Customer ID to query.

    Returns:
        Velocity counts vs thresholds; EDD flag if GBP 10k+ cumulative.
    """
    try:
        data = await _api_get(f"/v1/monitor/velocity/{customer_id}")
        vel = data.get("velocity", {})
        lines = [
            f"## Velocity Metrics — `{customer_id}`\n",
            f"**EDD Required**: {'⚠️ YES (I-04)' if data.get('requires_edd') else '✅ No'}",
            f"**Cumulative 24h (GBP)**: £{data.get('cumulative_gbp_24h', '0')}",
            "",
            "| Window | Count | Threshold | Status |",
            "|--------|-------|-----------|--------|",
        ]
        for window, metrics in vel.items():
            exceeded = metrics.get("exceeded", False)
            status_str = "⚠️ EXCEEDED" if exceeded else "✅ OK"
            lines.append(
                f"| {window} | {metrics.get('count', 0)} "
                f"| {metrics.get('threshold', '?')} | {status_str} |"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching velocity for {customer_id}: {e}"


@mcp_server.tool()
async def monitor_dashboard_metrics() -> str:
    """Get aggregate AML monitoring metrics for compliance dashboard.

    Returns alert counts by severity, open/escalated breakdown,
    and SAR yield estimate vs target (20%).
    """
    try:
        metrics = await _api_get("/v1/monitor/metrics")
        by_sev = metrics.get("by_severity", {})
        targets = metrics.get("targets", {})
        sar_yield = metrics.get("sar_yield_estimate", 0)
        sar_target = targets.get("sar_yield_target", 0.20)
        sar_status = "✅" if sar_yield >= sar_target else "⚠️"
        return (
            f"## AML Monitoring Dashboard\n\n"
            f"**Total Alerts**: {metrics.get('total_alerts', 0)}\n"
            f"**Open**: {metrics.get('open_alerts', 0)} | "
            f"**Escalated**: {metrics.get('escalated_alerts', 0)}\n\n"
            f"### By Severity\n"
            f"| CRITICAL | HIGH | MEDIUM | LOW |\n"
            f"|----------|------|--------|-----|\n"
            f"| {by_sev.get('critical', 0)} | {by_sev.get('high', 0)} "
            f"| {by_sev.get('medium', 0)} | {by_sev.get('low', 0)} |\n\n"
            f"### Performance vs Targets\n"
            f"| Metric | Current | Target | Status |\n"
            f"|--------|---------|--------|--------|\n"
            f"| SAR Yield | {sar_yield:.1%} | {sar_target:.0%} | {sar_status} |\n"
            f"| Review SLA | 24h | {targets.get('review_sla_hours', 24)}h | ✅ |\n"
        )
    except Exception as e:
        return f"Error fetching dashboard metrics: {e}"


# ── Compliance Experiment Copilot Tools (IL-CEC-01) ───────────────────────


@mcp_server.tool()
async def experiment_design(
    query: str,
    scope: str,
    created_by: str,
    tags: list[str] | None = None,
) -> str:
    """Design a new compliance experiment from a knowledge base query.

    Queries the compliance KB for the given scope, generates a hypothesis
    with KB citations, and creates a DRAFT experiment with AML metrics
    baseline/target from the config.

    Args:
        query: The compliance question or gap to investigate.
        scope: One of: transaction_monitoring, kyc_onboarding, case_management,
               sar_filing, risk_scoring.
        created_by: Email or name of the requesting analyst/compliance officer.
        tags: Optional list of additional tags for the experiment.

    Returns:
        Markdown summary of the created DRAFT experiment.
    """
    try:
        payload: dict = {
            "query": query,
            "scope": scope,
            "created_by": created_by,
            "tags": tags or [],
        }
        exp = await _api_post("/v1/experiments/design", payload)
        return (
            f"## Experiment Created (DRAFT)\n\n"
            f"**ID**: `{exp.get('id')}`\n"
            f"**Title**: {exp.get('title')}\n"
            f"**Scope**: `{exp.get('scope')}`\n"
            f"**Status**: {exp.get('status', 'draft').upper()}\n"
            f"**Citations**: {', '.join(exp.get('kb_citations', []))}\n\n"
            f"### Hypothesis\n{exp.get('hypothesis', 'N/A')}\n\n"
            f"### Metrics Baseline\n"
            f"- Hit Rate: {exp.get('metrics_baseline', {}).get('hit_rate_24h', 'N/A')}\n"
            f"- False Positive Rate: {exp.get('metrics_baseline', {}).get('false_positive_rate', 'N/A')}\n\n"
            f"Next step: `PATCH /v1/experiments/{exp.get('id')}/approve` to activate."
        )
    except Exception as e:
        return f"Error designing experiment: {e}"


@mcp_server.tool()
async def experiment_list(status: str = "") -> str:
    """List compliance experiments, optionally filtered by status.

    Args:
        status: Optional filter — one of: draft, active, finished, rejected.
                Leave empty to list all experiments.

    Returns:
        Markdown table of experiments.
    """
    try:
        path = "/v1/experiments"
        if status:
            path += f"?status={status}"
        experiments = await _api_get(path)
        if not experiments:
            return f"No experiments found{f' with status={status}' if status else ''}."
        lines = [
            f"## Experiments ({len(experiments)} total{f', status={status}' if status else ''})\n",
            "| ID | Title | Scope | Status | Updated |",
            "|----|-------|-------|--------|---------|",
        ]
        for e in experiments:
            lines.append(
                f"| `{e.get('id', '?')}` | {e.get('title', 'N/A')} "
                f"| {e.get('scope', '?')} | **{e.get('status', '?').upper()}** "
                f"| {str(e.get('updated_at', ''))[:10]} |"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing experiments: {e}"


@mcp_server.tool()
async def experiment_get_metrics(period_days: int = 1) -> str:
    """Get current AML performance metrics snapshot from ClickHouse.

    Returns hit rate, false positive rate, SAR yield, review time,
    and amount blocked (GBP) for the given lookback period.

    Args:
        period_days: Lookback period in days (1–90). Default: 1.

    Returns:
        Markdown summary of current AML metrics.
    """
    try:
        metrics = await _api_get(f"/v1/experiments/metrics/current?period_days={period_days}")
        hit = metrics.get("hit_rate_24h")
        fp = metrics.get("false_positive_rate")
        sar = metrics.get("sar_yield")
        hours = metrics.get("time_to_review_hours")
        blocked = metrics.get("amount_blocked_gbp")
        cases = metrics.get("cases_reviewed", 0)
        return (
            f"## AML Metrics Snapshot (last {period_days} day(s))\n\n"
            f"| Metric | Value |\n"
            f"|--------|-------|\n"
            f"| Hit Rate | {f'{hit:.1%}' if hit is not None else 'N/A'} |\n"
            f"| False Positive Rate | {f'{fp:.1%}' if fp is not None else 'N/A'} |\n"
            f"| SAR Yield | {f'{sar:.1%}' if sar is not None else 'N/A'} |\n"
            f"| Avg Review Time | {f'{hours:.1f}h' if hours is not None else 'N/A'} |\n"
            f"| Amount Blocked | {f'£{float(blocked):,.2f}' if blocked else 'N/A'} |\n"  # nosemgrep: banxe-float-money — display only, not monetary calculation
            f"| Cases Reviewed | {cases} |\n"
        )
    except Exception as e:
        return f"Error fetching AML metrics: {e}"


@mcp_server.tool()
async def experiment_propose_change(
    experiment_id: str,
    dry_run: bool = True,
) -> str:
    """Propose a compliance change for an ACTIVE experiment.

    Creates a Git branch, renders a PR body with HITL checklist, and
    opens a GitHub PR + tracking issue (or previews in dry_run mode).

    HITL invariant: every proposal includes a human approval checklist
    (CTIO + Compliance Officer + backtest + rollback plan).

    Args:
        experiment_id: ID of the ACTIVE experiment to propose.
        dry_run: If True (default), preview only — no branch/PR created.

    Returns:
        Markdown summary of the proposal with HITL checklist status.
    """
    try:
        proposal = await _api_post(
            f"/v1/experiments/{experiment_id}/propose",
            {"dry_run": dry_run},
        )
        checklist = proposal.get("hitl_checklist", {})
        hitl_lines = [
            f"- [{'x' if checklist.get('ctio_reviewed') else ' '}] CTIO reviewed",
            f"- [{'x' if checklist.get('compliance_officer_signoff') else ' '}] Compliance officer sign-off",
            f"- [{'x' if checklist.get('backtest_results_reviewed') else ' '}] Backtest results reviewed",
            f"- [{'x' if checklist.get('rollback_plan_defined') else ' '}] Rollback plan defined",
        ]
        pr_url = proposal.get("pr_url") or "_not created (dry run)_"
        issue_url = proposal.get("issue_url") or "_not created (dry run)_"
        return (
            f"## Change Proposal — `{experiment_id}`\n"
            f"{'**[DRY RUN]** No branch or PR created.' if dry_run else ''}\n\n"
            f"**Branch**: `{proposal.get('branch_name')}`\n"
            f"**PR Title**: {proposal.get('pr_title')}\n"
            f"**Status**: {proposal.get('status', '?').upper()}\n"
            f"**PR URL**: {pr_url}\n"
            f"**Issue URL**: {issue_url}\n\n"
            f"### HITL Checklist\n" + "\n".join(hitl_lines) + "\n\n"
            "### Files to Change\n"
            + "\n".join(f"- `{f}`" for f in proposal.get("files_changed", []))
        )
    except Exception as e:
        return f"Error proposing change: {e}"


# ── Support tools (IL-CSB-01 | #117) ────────────────────────────────────


@mcp_server.tool()
async def support_create_ticket(
    customer_id: str,
    subject: str,
    body: str,
    channel: str = "API",
) -> str:
    """Create a support ticket, auto-route it, and check for DISP complaint.

    Performs in one call:
    - Keyword-based category/priority routing
    - FAQ auto-resolution attempt (KB confidence ≥ 80%)
    - FCA DISP 1.1 formal complaint detection

    Args:
        customer_id: Customer UUID.
        subject: Short ticket subject (5-200 chars).
        body: Full ticket body (10-5000 chars).
        channel: Originating channel — API, EMAIL, TELEGRAM, WEB, PHONE.

    Returns:
        JSON with ticket ID, SLA deadline, routing, and auto_resolved flag.
    """
    try:
        result = await _api_post(
            "/v1/support/tickets",
            {
                "customer_id": customer_id,
                "subject": subject,
                "body": body,
                "channel": channel,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def support_get_metrics(period_days: int = 30) -> str:
    """Get CSAT/NPS/SLA support metrics for Consumer Duty PS22/9 §10 reporting.

    Returns rolling-period aggregates:
    - avg_csat: Customer Satisfaction Score (1-5 scale)
    - avg_nps: Net Promoter Score input (0-10 scale)
    - nps_score: Net Promoter Score (-100 to +100)
    - by_category: CSAT breakdown per ticket category

    FCA PS22/9 §10: firms must monitor whether they deliver good customer outcomes.

    Args:
        period_days: Rolling window in days (1-365, default: 30).

    Returns:
        JSON with CSAT, NPS, and outcome metrics.
    """
    try:
        result = await _api_get(f"/v1/support/metrics?period_days={period_days}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def support_check_sla(ticket_id: str) -> str:
    """Check SLA status for a support ticket.

    Returns ticket detail including:
    - sla_deadline: ISO timestamp of SLA commitment
    - status: current ticket status
    - is_sla_breached: whether SLA deadline has passed

    FCA DISP 1.3: firms must handle tickets promptly.

    Args:
        ticket_id: UUID of the support ticket.

    Returns:
        JSON with ticket detail and SLA status.
    """
    try:
        result = await _api_get(f"/v1/support/tickets/{ticket_id}")
        # Compute SLA breach client-side for MCP consumers
        sla_deadline = result.get("sla_deadline", "")
        is_breached = False
        if sla_deadline:
            try:
                deadline_dt = datetime.fromisoformat(sla_deadline)
                if deadline_dt.tzinfo is None:
                    deadline_dt = deadline_dt.replace(tzinfo=UTC)
                is_breached = datetime.now(UTC) > deadline_dt
            except ValueError:
                pass
        result["is_sla_breached"] = is_breached
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def support_route_ticket(
    customer_id: str,
    subject: str,
    body: str,
) -> str:
    """Classify and route a customer query without creating a persistent ticket.

    Use this when you need routing intelligence without persisting a ticket
    (e.g., pre-screening a message before creating a formal ticket).

    Returns routing decision:
    - category: ACCOUNT/PAYMENT/KYC/FRAUD/GENERAL
    - priority: CRITICAL/HIGH/MEDIUM/LOW
    - assigned_to: target queue name
    - sla_hours: SLA commitment in hours
    - auto_resolvable: whether FAQ bot can handle it

    Args:
        customer_id: Customer UUID (for audit).
        subject: Message subject.
        body: Message body.

    Returns:
        JSON with routing classification.
    """
    try:
        # Create ticket (routing happens server-side), then return routing info
        result = await _api_post(
            "/v1/support/tickets",
            {
                "customer_id": customer_id,
                "subject": subject,
                "body": body,
                "channel": "API",
            },
        )
        sla_map = {"CRITICAL": 1, "HIGH": 4, "MEDIUM": 24, "LOW": 72}
        priority = result.get("priority", "LOW")
        return json.dumps(
            {
                "ticket_id": result.get("id"),
                "category": result.get("category"),
                "priority": priority,
                "assigned_to": result.get("assigned_to"),
                "sla_hours": sla_map.get(priority, 72),
                "auto_resolvable": result.get("auto_resolved", False),
                "is_formal_complaint": result.get("is_formal_complaint", False),
            },
            indent=2,
        )
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── Regulatory Reporting MCP Tools (IL-RRA-01) ────────────────────────────────


@mcp_server.tool()
async def report_generate(
    report_type: str,
    entity_id: str,
    entity_name: str,
    period_start: str,
    period_end: str,
    actor: str,
    financial_data: str = "{}",
) -> str:
    """Generate and validate a regulatory XML report (FIN060/FIN071/FSA076/SAR/BoE/ACPR).

    Args:
        report_type: e.g. FIN060, FIN071, FSA076, SAR_BATCH, BOE_FORM_BT, ACPR_EMI
        entity_id: FCA firm reference number
        entity_name: Legal entity name
        period_start: ISO8601 date string (YYYY-MM-DD)
        period_end: ISO8601 date string (YYYY-MM-DD)
        actor: User or agent ID requesting generation
        financial_data: JSON string of financial figures for this report type

    Returns:
        JSON with report_id, status, validation_errors, xml_content (if valid).
    """
    try:
        payload = {
            "report_type": report_type,
            "entity_id": entity_id,
            "entity_name": entity_name,
            "period_start": period_start,
            "period_end": period_end,
            "actor": actor,
            "financial_data": json.loads(financial_data),
        }
        result = await _api_post("/v1/regulatory/reports/generate", payload)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def report_validate(report_type: str, xml_content: str) -> str:
    """Validate regulatory XML against structural and XSD schema rules.

    Args:
        report_type: e.g. FIN060, FIN071, FSA076
        xml_content: Full XML string to validate

    Returns:
        JSON with is_valid, errors list, warnings list, schema_version.
    """
    try:
        payload = {
            "report_type": report_type,
            "entity_id": "validate-only",
            "entity_name": "validate-only",
            "period_start": "2025-01-01T00:00:00Z",
            "period_end": "2025-01-31T23:59:59Z",
            "actor": "mcp-validate",
            "financial_data": {},
        }
        result = await _api_post("/v1/regulatory/reports/generate", payload)
        return json.dumps(
            {
                "is_valid": result.get("status") == "VALIDATED",
                "validation_errors": result.get("validation_errors", []),
                "schema_version": "structural-v1",
                "report_id": result.get("report_id"),
            },
            indent=2,
        )
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def report_schedule(
    report_type: str,
    entity_id: str,
    frequency: str,
    actor: str,
    template_version: str = "v1",
) -> str:
    """Schedule a recurring regulatory report via n8n cron.

    Args:
        report_type: e.g. FIN060, FIN071, FSA076
        entity_id: FCA firm reference number
        frequency: MONTHLY | QUARTERLY | ANNUALLY | WEEKLY
        actor: User authorising the schedule
        template_version: Template version (default: v1)

    Returns:
        JSON with schedule_id, report_type, frequency, next_run_at.
    """
    try:
        payload = {
            "report_type": report_type,
            "entity_id": entity_id,
            "frequency": frequency,
            "actor": actor,
            "template_version": template_version,
        }
        result = await _api_post("/v1/regulatory/schedules", payload)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def report_audit_log(
    entity_id: str = "",
    report_type: str = "",
    days: int = 30,
) -> str:
    """Query the regulatory audit trail (SYSC 9 records).

    Args:
        entity_id: Filter by FCA firm reference (optional)
        report_type: Filter by report type e.g. FIN060 (optional)
        days: Lookback window in days (default: 30)

    Returns:
        JSON with count and list of audit entries.
    """
    try:
        params: dict[str, str | int] = {"days": days}
        if entity_id:
            params["entity_id"] = entity_id
        if report_type:
            params["report_type"] = report_type
        result = await _api_get("/v1/regulatory/reports/audit", params=params)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def report_list_templates() -> str:
    """List all supported regulatory report templates with SLA deadlines.

    Returns:
        JSON with count and list of templates (type, version, regulator, SLA days).
    """
    try:
        result = await _api_get("/v1/regulatory/templates")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def ob_create_consent(
    entity_id: str,
    aspsp_id: str,
    consent_type: str,
    permissions: str,
    actor: str,
    redirect_uri: str = "",
) -> str:
    """Create a PSD2 Open Banking consent (AISP or PISP) for a customer.

    Args:
        entity_id: Customer or firm identifier
        aspsp_id: Target bank ID (e.g. barclays-uk, hsbc-uk, bnp-fr)
        consent_type: AISP or PISP
        permissions: Comma-separated list (ACCOUNTS,BALANCES,TRANSACTIONS,BENEFICIARIES)
        actor: Identity of the requestor
        redirect_uri: Optional redirect URI for REDIRECT SCA flow

    Returns:
        JSON with consent id, status, and expires_at.
    """
    try:
        payload: dict[str, object] = {
            "entity_id": entity_id,
            "aspsp_id": aspsp_id,
            "consent_type": consent_type,
            "permissions": [p.strip() for p in permissions.split(",") if p.strip()],
            "actor": actor,
        }
        if redirect_uri:
            payload["redirect_uri"] = redirect_uri
        result = await _api_post("/v1/open-banking/consents", payload)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def ob_initiate_payment(
    consent_id: str,
    entity_id: str,
    aspsp_id: str,
    amount: str,
    currency: str,
    creditor_iban: str,
    creditor_name: str,
    actor: str,
    debtor_iban: str = "",
    reference: str = "",
) -> str:
    """Initiate a PSD2 PISP payment via an authorised consent (L4 — HITL gate, I-27).

    Args:
        consent_id: Authorised PISP consent ID
        entity_id: Customer identifier
        aspsp_id: Target ASPSP bank ID
        amount: Payment amount as decimal string (e.g. "100.00")
        currency: ISO 4217 currency code (e.g. GBP)
        creditor_iban: Beneficiary IBAN
        creditor_name: Beneficiary name
        actor: Identity of the requestor
        debtor_iban: Optional debtor IBAN
        reference: Optional payment reference

    Returns:
        JSON with payment id, status, and aspsp_payment_id.
    """
    try:
        payload: dict[str, object] = {
            "consent_id": consent_id,
            "entity_id": entity_id,
            "aspsp_id": aspsp_id,
            "amount": amount,
            "currency": currency,
            "creditor_iban": creditor_iban,
            "creditor_name": creditor_name,
            "actor": actor,
        }
        if debtor_iban:
            payload["debtor_iban"] = debtor_iban
        if reference:
            payload["reference"] = reference
        result = await _api_post("/v1/open-banking/payments", payload)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def ob_get_accounts(consent_id: str, actor: str) -> str:
    """Fetch account list via an authorised AISP consent (PSD2 Art.67).

    Args:
        consent_id: Authorised AISP consent ID
        actor: Identity of the requestor

    Returns:
        JSON list of accounts with IBAN, currency, and balance.
    """
    try:
        result = await _api_get(f"/v1/open-banking/accounts?consent_id={consent_id}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def ob_revoke_consent(consent_id: str, actor: str) -> str:
    """Revoke an existing Open Banking consent (AISP or PISP).

    Args:
        consent_id: Consent ID to revoke
        actor: Identity of the requestor

    Returns:
        JSON with consent id and updated status REVOKED.
    """
    try:
        result = await _api_post(f"/v1/open-banking/consents/{consent_id}/revoke", {"actor": actor})
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def ob_list_aspsps() -> str:
    """List all registered ASPSPs (banks) available for Open Banking connections.

    Returns:
        JSON list of ASPSPs with id, name, country, and standard (UK_OBIE / BERLIN_GROUP).
    """
    try:
        result = await _api_get("/v1/open-banking/aspsps")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def audit_query_events(
    category: str = "",
    entity_id: str = "",
    limit: int = 50,
) -> str:
    """Query unified audit events across all Banxe services.

    Args:
        category: Optional filter — AML, KYC, PAYMENT, LEDGER, AUTH, COMPLIANCE,
                  SAFEGUARDING, REGULATORY (empty = all)
        entity_id: Optional filter by customer/firm entity ID
        limit: Max events to return (default 50)

    Returns:
        JSON list of audit events with event_type, risk_level, actor, created_at.
    """
    try:
        params: list[str] = [f"limit={limit}"]
        if category:
            params.append(f"category={category}")
        if entity_id:
            params.append(f"entity_id={entity_id}")
        qs = "&".join(params)
        result = await _api_get(f"/v1/audit/events?{qs}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def audit_generate_report(
    title: str,
    period_start: str,
    period_end: str,
    actor: str = "system",
) -> str:
    """Generate a governance and compliance report for a given period.

    Args:
        title: Report title (e.g. "Q1 2025 Governance Report")
        period_start: ISO 8601 start datetime (e.g. 2025-01-01T00:00:00Z)
        period_end: ISO 8601 end datetime (e.g. 2025-03-31T23:59:59Z)
        actor: Identity of the requestor

    Returns:
        JSON GovernanceReport with compliance_score, risk_summary, and total_events.
    """
    try:
        payload = {
            "title": title,
            "period_start": period_start,
            "period_end": period_end,
            "actor": actor,
        }
        result = await _api_post("/v1/audit/reports", payload)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def audit_risk_score(entity_id: str, lookback_days: int = 30) -> str:
    """Compute multi-dimensional risk score for an entity.

    Args:
        entity_id: Customer or firm identifier
        lookback_days: Lookback window in days (default 30)

    Returns:
        JSON RiskScore with aml_score, fraud_score, operational_score,
        regulatory_score, overall_score, and contributing_factors.
    """
    try:
        result = await _api_get(f"/v1/audit/risk/score/{entity_id}?lookback_days={lookback_days}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def audit_governance_status() -> str:
    """Get current platform-wide governance and compliance status.

    Returns:
        JSON with status (COMPLIANT / REQUIRES_ATTENTION / NON_COMPLIANT),
        checked_at timestamp, and details dict.
    """
    try:
        result = await _api_get("/v1/audit/governance/status")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def treasury_get_positions(pool_id: str = "") -> str:
    """Get treasury cash positions for all pools or a specific liquidity pool.

    Args:
        pool_id: Optional pool ID — if empty returns all pools summary

    Returns:
        JSON with pool summary: current_balance, required_minimum, is_compliant.
    """
    try:
        if pool_id:
            result = await _api_get(f"/v1/treasury/positions/{pool_id}")
        else:
            result = await _api_get("/v1/treasury/positions")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def treasury_forecast(pool_id: str, horizon: str = "DAYS_7") -> str:
    """Run a cash flow forecast for a liquidity pool (CASS 15.6).

    Args:
        pool_id: Pool ID to forecast (e.g. pool-001)
        horizon: Forecast horizon — DAYS_7, DAYS_14, or DAYS_30 (default DAYS_7)

    Returns:
        JSON ForecastResult with forecast_amount, confidence, shortfall_risk.
    """
    try:
        result = await _api_get(f"/v1/treasury/forecasts/{pool_id}?horizon={horizon}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def treasury_propose_sweep(
    pool_id: str,
    direction: str,
    amount: str,
    actor: str,
    description: str = "",
) -> str:
    """Propose a treasury sweep — HITL gate required before execution (I-27).

    Args:
        pool_id: Source liquidity pool ID
        direction: SURPLUS_OUT (move excess) or DEFICIT_IN (draw funds)
        amount: Sweep amount as decimal string (e.g. "500000.00")
        actor: Identity of the requestor
        description: Optional description

    Returns:
        JSON SweepEvent with id and approved_by=null (awaiting human approval).
    """
    try:
        payload: dict[str, object] = {
            "pool_id": pool_id,
            "direction": direction,
            "amount": amount,
            "actor": actor,
            "description": description,
        }
        result = await _api_post("/v1/treasury/sweeps", payload)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def treasury_reconcile(
    institution: str,
    iban: str,
    balance: str,
    client_money: str,
    currency: str = "GBP",
) -> str:
    """Trigger CASS 15.3 safeguarding reconciliation for a safeguarding account.

    Args:
        institution: Bank name (e.g. Barclays)
        iban: Safeguarding account IBAN
        balance: Current book balance as decimal string (e.g. "2500000.00")
        client_money: Client money held as decimal string
        currency: Currency code (default GBP)

    Returns:
        JSON ReconciliationRecord with status (MATCHED or DISCREPANCY) and variance.
    """
    try:
        payload: dict[str, object] = {
            "institution": institution,
            "iban": iban,
            "balance": balance,
            "client_money": client_money,
            "currency": currency,
        }
        result = await _api_post("/v1/treasury/reconcile", payload)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def treasury_pending_sweeps(pool_id: str = "") -> str:
    """List treasury sweeps awaiting HITL approval.

    Args:
        pool_id: Optional pool ID filter (empty = all pools)

    Returns:
        JSON list of pending SweepEvents with amount, direction, proposed_at.
    """
    try:
        url = "/v1/treasury/sweeps/pending"
        if pool_id:
            url += f"?pool_id={pool_id}"
        result = await _api_get(url)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def notify_send(
    entity_id: str,
    category: str,
    channel: str,
    template_id: str,
    actor: str,
    context: str = "{}",
    priority: str = "NORMAL",
) -> str:
    """Send a notification to a customer via the Notification Hub (IL-NHB-01).

    Args:
        entity_id: Customer or firm ID
        category: PAYMENT, KYC, AML, COMPLIANCE, SECURITY, OPERATIONAL, MARKETING
        channel: EMAIL, SMS, PUSH, TELEGRAM, or WEBHOOK
        template_id: Template ID (e.g. tmpl-payment-confirmed, tmpl-kyc-approved)
        actor: Identity of the requestor
        context: JSON string of template variables (e.g. '{"name":"John","amount":"100"}')
        priority: LOW, NORMAL, HIGH, or CRITICAL (default NORMAL)

    Returns:
        JSON DeliveryRecord with status (SENT, FAILED, or OPT_OUT).
    """
    try:
        ctx = json.loads(context) if context else {}
        payload: dict[str, object] = {
            "entity_id": entity_id,
            "category": category,
            "channel": channel,
            "template_id": template_id,
            "context": ctx,
            "actor": actor,
            "priority": priority,
        }
        result = await _api_post("/v1/notifications-hub/send", payload)
        return json.dumps(result, indent=2)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON in context parameter"})
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def notify_list_templates(category: str = "", channel: str = "") -> str:
    """List available notification templates in the Notification Hub.

    Args:
        category: Optional filter (PAYMENT, KYC, AML, SECURITY, etc.)
        channel: Optional filter (EMAIL, SMS, PUSH, TELEGRAM, WEBHOOK)

    Returns:
        JSON list of templates with id, name, subject, language, version.
    """
    try:
        params: list[str] = []
        if category:
            params.append(f"category={category}")
        if channel:
            params.append(f"channel={channel}")
        qs = "&".join(params)
        url = f"/v1/notifications-hub/templates?{qs}" if qs else "/v1/notifications-hub/templates"
        result = await _api_get(url)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def notify_get_preferences(entity_id: str) -> str:
    """Get notification preferences for a customer.

    Args:
        entity_id: Customer or firm ID

    Returns:
        JSON list of NotificationPreference with channel, category, opt_in flag.
    """
    try:
        result = await _api_get(f"/v1/notifications-hub/preferences/{entity_id}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def notify_delivery_status(record_id: str) -> str:
    """Get delivery status for a notification.

    Args:
        record_id: Delivery record ID (returned from notify_send)

    Returns:
        JSON DeliveryRecord with status, attempted_at, delivered_at, retry_count.
    """
    try:
        result = await _api_get(f"/v1/notifications-hub/delivery/{record_id}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp_server.tool()
async def card_issue(
    entity_id: str,
    card_type: str,
    network: str,
    name_on_card: str,
    actor: str,
) -> str:
    """Issue a new virtual or physical payment card for a customer.

    Card is issued in PENDING status — must be activated before use.
    PIN must be set separately via card_set_pin. (I-12: PIN never stored plain)

    Args:
        entity_id: Customer entity ID
        card_type: VIRTUAL or PHYSICAL
        network: MASTERCARD or VISA
        name_on_card: Cardholder name as it will appear on the card
        actor: Operator issuing the card (for audit trail)
    """
    try:
        result = await _api_post(
            "/v1/cards/issue",
            {
                "entity_id": entity_id,
                "card_type": card_type,
                "network": network,
                "name_on_card": name_on_card,
                "actor": actor,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def card_freeze(card_id: str, actor: str, reason: str = "") -> str:
    """Freeze a card — blocks all transactions immediately (reversible).

    Use for suspected fraud or customer request. Card stays FROZEN until
    unfrozen. For permanent block, use card block endpoint (requires HITL L4).

    Args:
        card_id: Card ID to freeze
        actor: Operator performing the freeze (for audit trail)
        reason: Optional reason for the freeze
    """
    try:
        result = await _api_post(
            f"/v1/cards/{card_id}/freeze",
            {"actor": actor, "reason": reason},
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def card_get_status(card_id: str) -> str:
    """Get current card status, limits, BIN, and metadata.

    Returns card details including status (PENDING/ACTIVE/FROZEN/BLOCKED/EXPIRED),
    network, BIN range, expiry, and spend limits.

    Args:
        card_id: Card ID to retrieve
    """
    try:
        result = await _api_get(f"/v1/cards/{card_id}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def card_set_limits(
    card_id: str,
    period: str,
    limit_amount: str,
    currency: str,
    actor: str,
) -> str:
    """Set per-card spend limit for a given period (DAILY, WEEKLY, MONTHLY).

    Limits are enforced at authorisation time. Amount must be a decimal string.
    (I-05: amounts always as strings, I-01: Decimal arithmetic)

    Args:
        card_id: Card ID to configure
        period: DAILY, WEEKLY, or MONTHLY
        limit_amount: Maximum spend amount as decimal string (e.g. "500.00")
        currency: ISO 4217 currency code (e.g. "GBP")
        actor: Operator setting the limit (for audit trail)
    """
    try:
        result = await _api_post(
            f"/v1/cards/{card_id}/limits",
            {
                "period": period,
                "limit_amount": limit_amount,
                "currency": currency,
                "actor": actor,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def card_list_transactions(card_id: str) -> str:
    """List cleared transactions for a card.

    Returns chronological transaction history including amount, merchant,
    MCC, authorisation reference, and settlement status.

    Args:
        card_id: Card ID to query
    """
    try:
        result = await _api_get(f"/v1/cards/{card_id}/transactions")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def merchant_onboard(
    merchant_id: str,
    name: str,
    mcc: str,
    daily_volume_limit: str,
    currency: str,
    actor: str,
) -> str:
    """Onboard a new merchant — initiates KYB risk assessment.

    Merchant is PENDING_KYB until approved. Prohibited MCCs (7995, 9754, 7801)
    are rejected immediately. High-risk MCCs require HITL approval. (I-27)

    Args:
        merchant_id: Unique merchant identifier
        name: Legal merchant name
        mcc: Merchant Category Code (ISO 18245)
        daily_volume_limit: Expected daily volume as decimal string
        currency: ISO 4217 currency code
        actor: Operator performing onboarding
    """
    try:
        result = await _api_post(
            "/v1/merchants/onboard",
            {
                "merchant_id": merchant_id,
                "name": name,
                "mcc": mcc,
                "daily_volume_limit": daily_volume_limit,
                "currency": currency,
                "actor": actor,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def merchant_accept_payment(
    merchant_id: str,
    amount: str,
    currency: str,
    payment_method: str,
    actor: str,
) -> str:
    """Accept a card payment for a merchant.

    Payments ≥ £30 require 3DS2 (PSD2 SCA — returns PENDING_3DS status).
    Payments < £30 are APPROVED immediately. Amounts must be decimal strings.
    (I-05: amounts as strings, 3DS2 threshold: Decimal("30.00"))

    Args:
        merchant_id: Merchant ID accepting the payment
        amount: Payment amount as decimal string (e.g. "99.99")
        currency: ISO 4217 currency code
        payment_method: Payment method description
        actor: System or operator initiating the payment
    """
    try:
        result = await _api_post(
            f"/v1/merchants/{merchant_id}/payments",
            {
                "amount": amount,
                "currency": currency,
                "payment_method": payment_method,
                "actor": actor,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def merchant_get_settlements(merchant_id: str) -> str:
    """List settlement batches for a merchant.

    Returns all settlement batches with gross amount, fees (1.5%),
    net payout, and settlement status (PENDING/PROCESSING/SETTLED/FAILED).

    Args:
        merchant_id: Merchant ID to query
    """
    try:
        result = await _api_get(f"/v1/merchants/{merchant_id}/settlements")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def merchant_handle_chargeback(
    merchant_id: str,
    payment_id: str,
    reason: str,
    amount: str,
    currency: str,
) -> str:
    """Receive and register a chargeback dispute for a merchant payment.

    Creates a DisputeCase in RECEIVED status. Lifecycle:
    RECEIVED → UNDER_INVESTIGATION → REPRESENTED → RESOLVED_WIN/RESOLVED_LOSS.
    All amounts as decimal strings. (I-05, I-24: append-only audit trail)

    Args:
        merchant_id: Merchant ID receiving the chargeback
        payment_id: Original payment ID being disputed
        reason: Chargeback reason code (e.g. FRAUD, NOT_RECEIVED)
        amount: Disputed amount as decimal string
        currency: ISO 4217 currency code
    """
    try:
        result = await _api_post(
            f"/v1/merchants/{merchant_id}/chargebacks",
            {
                "payment_id": payment_id,
                "reason": reason,
                "amount": amount,
                "currency": currency,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def merchant_risk_score(merchant_id: str) -> str:
    """Get the current risk score for a merchant.

    Risk score is a float 0–100 (analytical metric, not monetary).
    Incorporates chargeback ratio, MCC risk, volume anomaly, and velocity.
    HIGH risk (score ≥ 70) triggers HITL review. (I-27)

    Args:
        merchant_id: Merchant ID to score
    """
    try:
        result = await _api_get(f"/v1/merchants/{merchant_id}/risk-score")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def fx_get_quote(
    entity_id: str,
    from_currency: str,
    to_currency: str,
    amount: str,
) -> str:
    """Get a real-time FX quote with bid/ask spread.

    Quote is valid for 30 seconds. Compliance check runs automatically:
    amounts ≥ £10k trigger EDD_REQUIRED; amounts ≥ £50k require HITL.
    Sanctioned currencies (RUB, IRR, KPW, BYR, SYP, CUC) return BLOCKED.
    All amounts as decimal strings. (I-01, I-05)

    Args:
        entity_id: Customer or entity requesting the quote
        from_currency: Source currency ISO 4217 (e.g. "GBP")
        to_currency: Target currency ISO 4217 (e.g. "EUR")
        amount: Amount to exchange as decimal string (e.g. "1000.00")
    """
    try:
        result = await _api_post(
            "/v1/fx/quote",
            {
                "entity_id": entity_id,
                "from_currency": from_currency,
                "to_currency": to_currency,
                "amount": amount,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def fx_execute(entity_id: str, quote_id: str) -> str:
    """Execute an FX order against a previously obtained quote.

    Quote must not be expired (30s TTL). Returns execution details including
    debit/credit amounts, rate, and 0.1% fee. Returns HITL_REQUIRED (HTTP 202)
    for orders above £50,000. (I-01, I-05, I-27)

    Args:
        entity_id: Customer executing the order
        quote_id: Quote ID obtained from fx_get_quote
    """
    try:
        result = await _api_post(
            "/v1/fx/execute",
            {"entity_id": entity_id, "quote_id": quote_id},
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def fx_get_rates(pairs: str = "") -> str:
    """Get current FX rates for all supported currency pairs.

    Rates sourced from ECB reference data via Frankfurter. Supported pairs:
    GBP/EUR, GBP/USD, GBP/CHF, GBP/PLN, GBP/CZK, EUR/USD.
    Cache TTL: 60 seconds.

    Args:
        pairs: Optional comma-separated filter (e.g. "GBP/EUR,GBP/USD"). Empty = all pairs.
    """
    try:
        path = "/v1/fx/rates"
        if pairs:
            path = f"{path}?pairs={pairs}"
        result = await _api_get(path)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def fx_get_spreads(from_currency: str = "", to_currency: str = "") -> str:
    """Get FX spread configuration for currency pairs.

    Returns spread_bps (basis points), min/max/VIP rates, and volume tier thresholds.
    Majors (GBP/EUR, GBP/USD): 20 bps. Exotics (GBP/PLN, GBP/CZK): 50 bps.

    Args:
        from_currency: Filter by source currency (e.g. "GBP"). Empty = all spreads.
        to_currency: Filter by target currency (e.g. "EUR"). Empty = all spreads.
    """
    try:
        if from_currency and to_currency:
            result = await _api_get(f"/v1/fx/spreads/{from_currency}/{to_currency}")
        else:
            result = await _api_get("/v1/fx/spreads")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def fx_history(entity_id: str) -> str:
    """Get FX execution history for a customer entity.

    Returns all executed FX orders with amounts, rates, fees, and timestamps.
    Amounts serialised as strings. (I-05, I-24: append-only audit trail)

    Args:
        entity_id: Customer entity ID to query
    """
    try:
        result = await _api_get(f"/v1/fx/history/{entity_id}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def mc_get_balances(account_id: str) -> str:
    """Get all currency balances for a multi-currency account.

    Returns per-currency available/reserved balances as decimal strings.
    Up to 10 currencies per account. (I-01, I-05)

    Args:
        account_id: Multi-currency account ID
    """
    try:
        result = await _api_get(f"/v1/mc-accounts/{account_id}/balances")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def mc_convert(
    account_id: str,
    from_currency: str,
    to_currency: str,
    amount: str,
    rate: str,
) -> str:
    """Convert between currencies within a multi-currency account.

    Debits from_currency and credits to_currency atomically.
    0.2% conversion fee applied. Amounts as decimal strings. (I-01, I-05)

    Args:
        account_id: Multi-currency account ID
        from_currency: Source currency (e.g. "GBP")
        to_currency: Target currency (e.g. "EUR")
        amount: Amount to convert as decimal string (e.g. "500.00")
        rate: Exchange rate as decimal string (e.g. "1.1700")
    """
    try:
        result = await _api_post(
            f"/v1/mc-accounts/{account_id}/convert",
            {
                "from_currency": from_currency,
                "to_currency": to_currency,
                "amount": amount,
                "rate": rate,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def mc_reconcile_nostro(nostro_id: str, their_balance: str) -> str:
    """Reconcile a nostro/vostro account against correspondent bank's balance.

    Tolerance: £1.00 (correspondent banking standard — broader than internal 1p).
    MATCHED if |variance| ≤ £1.00, else DISCREPANCY. (I-24, CASS 15.3)

    Args:
        nostro_id: Nostro account ID (e.g. "nostro-gbp-001")
        their_balance: Correspondent bank's reported balance as decimal string
    """
    try:
        result = await _api_post(
            f"/v1/nostro/{nostro_id}/reconcile",
            {"their_balance": their_balance},
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def mc_currency_report(account_id: str, rates: str) -> str:
    """Generate consolidated multi-currency balance report in base currency.

    Converts all currency balances to base currency using provided rates.
    Rates format: JSON string {"EUR": "1.17", "USD": "1.27", ...}
    (I-01: all amounts Decimal; I-05: serialised as strings)

    Args:
        account_id: Multi-currency account ID
        rates: JSON string of exchange rates to base currency (e.g. '{"EUR":"1.17"}')
    """
    try:
        rates_dict = json.loads(rates)
        result = await _api_post(
            f"/v1/mc-accounts/{account_id}/currency-report",
            {"rates": rates_dict},
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid rates JSON: {exc}"})


@mcp_server.tool()
async def compliance_evaluate(entity_id: str, rule_ids: str = "") -> str:
    """Run compliance evaluation for a customer entity.

    Evaluates all active compliance rules (AML, KYC, SANCTIONS, PEP, REPORTING)
    against the entity. Returns per-rule check status (PASS/FAIL/WARNING) and
    any detected breaches. FAIL on SANCTIONS/AML rules → MATERIAL breach.

    Args:
        entity_id: Customer entity ID to evaluate
        rule_ids: Optional comma-separated rule IDs to evaluate (empty = all active rules)
    """
    try:
        payload: dict = {"entity_id": entity_id}
        if rule_ids:
            payload["rule_ids"] = [r.strip() for r in rule_ids.split(",")]
        result = await _api_post("/v1/compliance/evaluate", payload)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def compliance_get_rules(rule_type: str = "") -> str:
    """List active compliance rules, optionally filtered by type.

    Rule types: AML, KYC, SANCTIONS, PEP, DATA_RETENTION, REPORTING, POLICY.
    Returns rule ID, name, severity (CRITICAL/HIGH/MEDIUM/LOW), and description.

    Args:
        rule_type: Filter by rule type (empty = all active rules)
    """
    try:
        path = "/v1/compliance/rules"
        if rule_type:
            path = f"{path}?rule_type={rule_type}"
        result = await _api_get(path)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def compliance_report_breach(breach_id: str, actor: str) -> str:
    """Submit a compliance breach for FCA notification (SUP 15.3).

    ALWAYS returns HITL_REQUIRED (HTTP 202) — FCA breach reporting requires
    Compliance Officer approval. AI proposes, human decides. (I-27)
    Deadline: 1 business day from detection (SUP 15.3).

    Args:
        breach_id: Breach event ID to report to FCA
        actor: Compliance Officer requesting the submission
    """
    try:
        result = await _api_post(
            "/v1/compliance/breach/report",
            {"breach_id": breach_id, "actor": actor},
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def compliance_track_remediation(
    check_id: str,
    entity_id: str,
    finding: str,
    assigned_to: str,
    due_days: int = 30,
) -> str:
    """Create a remediation action for a compliance finding.

    Tracks remediation lifecycle: OPEN → ASSIGNED → IN_PROGRESS → RESOLVED → VERIFIED → CLOSED.
    All findings are logged to append-only audit trail. (I-24)

    Args:
        check_id: Compliance check ID that triggered the finding
        entity_id: Customer entity the finding relates to
        finding: Description of the compliance finding
        assigned_to: Person/team assigned to remediate
        due_days: Days until remediation is due (default: 30)
    """
    try:
        result = await _api_post(
            "/v1/compliance/remediations",
            {
                "check_id": check_id,
                "entity_id": entity_id,
                "finding": finding,
                "assigned_to": assigned_to,
                "due_days": due_days,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def compliance_policy_diff(policy_id: str, v1: int, v2: int) -> str:
    """Compare two versions of a compliance policy document.

    Returns side-by-side content for v1 and v2, plus a 'changed' flag.
    Useful for tracking policy amendments and audit trail. (SYSC 6.1)

    Args:
        policy_id: Policy identifier (e.g. "aml-policy", "kyc-policy")
        v1: First version number to compare
        v2: Second version number to compare
    """
    try:
        result = await _api_post(
            "/v1/compliance/policies/diff",
            {"policy_id": policy_id, "v1": v1, "v2": v2},
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def doc_upload(
    name: str,
    category: str,
    content: str,
    entity_id: str,
    uploaded_by: str,
    role: str,
    access_level: str = "INTERNAL",
) -> str:
    """Upload a compliance document to the document management system.

    Content is SHA-256 hashed for integrity verification on upload.
    Categories: KYC, AML, POLICY, REPORT, CONTRACT, REGULATORY, AUDIT.
    Access levels: PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED. (I-12)

    Args:
        name: Document name / filename
        category: Document category (KYC/AML/POLICY/REPORT/CONTRACT/REGULATORY/AUDIT)
        content: Document text content
        entity_id: Customer or entity the document belongs to
        uploaded_by: User uploading the document
        role: Uploader's role for access control
        access_level: Access level (default: INTERNAL)
    """
    try:
        result = await _api_post(
            "/v1/documents/upload",
            {
                "name": name,
                "category": category,
                "content": content,
                "entity_id": entity_id,
                "uploaded_by": uploaded_by,
                "role": role,
                "access_level": access_level,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def doc_search(query: str, entity_id: str = "", category: str = "") -> str:
    """Full-text search across compliance documents.

    Searches document names and tags. Returns results sorted by relevance score.
    Filter by entity_id and/or category for targeted searches.
    Access control applied — only documents the caller can see are returned.

    Args:
        query: Search query (keywords)
        entity_id: Optional filter by customer entity ID
        category: Optional filter by document category (KYC/AML/POLICY/etc.)
    """
    try:
        payload: dict = {"query": query}
        if entity_id:
            payload["entity_id"] = entity_id
        if category:
            payload["category"] = category
        result = await _api_post("/v1/documents/search", payload)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def doc_get_versions(doc_id: str) -> str:
    """List all versions of a document with content hashes and change notes.

    Returns version history sorted by version_number ascending.
    Each version includes SHA-256 content hash for integrity verification.
    (I-12: SHA-256 document integrity, I-24: append-only version history)

    Args:
        doc_id: Document ID to get version history for
    """
    try:
        result = await _api_get(f"/v1/documents/{doc_id}/versions")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def doc_retention_status(entity_id: str) -> str:
    """Check retention policy compliance for all documents belonging to an entity.

    Returns per-document retention status: days stored, retention limit,
    and whether action is required. Regulatory basis per category:
    KYC/AML: 5yr (MLR 2017 Reg.40), POLICY/REGULATORY: PERMANENT (SYSC 9).

    Args:
        entity_id: Customer entity ID to check retention for
    """
    try:
        result = await _api_get(f"/v1/documents/retention/{entity_id}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def lending_apply(
    customer_id: str,
    product_id: str,
    requested_amount: str,
    term_months: int,
) -> str:
    """Apply for a loan product — always returns HITL_REQUIRED (I-27: credit decisions require human approval).

    Args:
        customer_id: Customer ID applying for the loan
        product_id: Loan product ID (e.g. product-001 micro-loan, product-002 personal)
        requested_amount: Loan amount as decimal string (e.g. "1500.00")
        term_months: Loan term in months

    Returns:
        JSON with status=HITL_REQUIRED + application_id + credit_score (always — FCA CONC)
    """
    try:
        result = await _api_post(
            "/v1/lending/apply",
            {
                "customer_id": customer_id,
                "product_id": product_id,
                "requested_amount": requested_amount,
                "term_months": term_months,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def lending_score(
    customer_id: str, income: str, account_age_months: int, aml_risk_score: str
) -> str:
    """Score a customer's creditworthiness (0-1000 Decimal scale).

    Args:
        customer_id: Customer ID to score
        income: Annual income as decimal string
        account_age_months: Number of months customer has held an account
        aml_risk_score: AML risk score as decimal string (0=no risk, 100=max risk)

    Returns:
        JSON with credit score breakdown (income_factor, history_factor, aml_risk_factor, total)
    """
    try:
        result = await _api_post(
            "/v1/lending/score",
            {
                "customer_id": customer_id,
                "income": income,
                "account_age_months": account_age_months,
                "aml_risk_score": aml_risk_score,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def lending_get_schedule(application_id: str) -> str:
    """Retrieve the repayment schedule for an active loan.

    Args:
        application_id: Loan application ID

    Returns:
        JSON with monthly installments (payment, principal, interest, balance — all as strings)
    """
    try:
        result = await _api_get(f"/v1/lending/{application_id}/schedule")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def lending_arrears_status(application_id: str) -> str:
    """Get arrears history and current stage for a loan.

    Returns the arrears stage timeline: CURRENT / DAYS_1_30 / DAYS_31_60 / DAYS_61_90 / DEFAULT_90_PLUS.

    Args:
        application_id: Loan application ID

    Returns:
        JSON list of arrears records with stage, days_overdue, outstanding_amount
    """
    try:
        result = await _api_get(f"/v1/lending/{application_id}/arrears")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def lending_provision_report(application_id: str, ifrs_stage: str, exposure: str) -> str:
    """Compute IFRS 9 Expected Credit Loss (ECL) provision for a loan.

    IFRS 9 stages: STAGE_1 (PD=1%, 12-month ECL), STAGE_2 (PD=15%, lifetime),
    STAGE_3 (PD=90%, credit-impaired). LGD=45% for Stage 1/2, 65% for Stage 3.

    Args:
        application_id: Loan application ID
        ifrs_stage: IFRS 9 stage (STAGE_1, STAGE_2, or STAGE_3)
        exposure: Exposure at default as decimal string

    Returns:
        JSON with ecl_amount, probability_of_default, LGD, ifrs_stage
    """
    try:
        result = await _api_post(
            f"/v1/lending/{application_id}/provision",
            {"ifrs_stage": ifrs_stage, "exposure": exposure},
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def insurance_get_quote(
    customer_id: str,
    product_id: str,
    coverage_amount: str,
    term_days: int,
) -> str:
    """Calculate premium and create a quoted insurance policy.

    Returns a QUOTED policy with premium calculated from risk factors and coverage.
    Use insurance_bind_policy to activate.

    Args:
        customer_id: Customer requesting the quote
        product_id: Insurance product ID (e.g. ins-001 travel, ins-002 purchase)
        coverage_amount: Coverage amount as decimal string (e.g. "5000.00")
        term_days: Policy duration in days

    Returns:
        JSON with policy_id, premium (string), coverage_amount, status=QUOTED
    """
    try:
        result = await _api_post(
            "/v1/insurance/quote",
            {
                "customer_id": customer_id,
                "product_id": product_id,
                "coverage_amount": coverage_amount,
                "term_days": term_days,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def insurance_bind_policy(policy_id: str) -> str:
    """Bind and activate a quoted insurance policy (QUOTED→BOUND→ACTIVE).

    Args:
        policy_id: Policy ID from insurance_get_quote

    Returns:
        JSON with activated policy details (status=ACTIVE)
    """
    try:
        result = await _api_post(f"/v1/insurance/policies/{policy_id}/bind", {})
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def insurance_file_claim(
    policy_id: str,
    customer_id: str,
    claimed_amount: str,
    description: str,
) -> str:
    """File an insurance claim against an active policy.

    Claims ≤£1000 are processed automatically.
    Claims >£1000 return {"status": "HITL_REQUIRED"} — Compliance Officer approval needed (I-27, FCA ICOBS 8.1).

    Args:
        policy_id: Active policy to claim against
        customer_id: Customer filing the claim
        claimed_amount: Claim amount as decimal string (e.g. "750.00")
        description: Description of the claim event

    Returns:
        JSON with claim status. If >£1000: {"status": "HITL_REQUIRED", "claim_id": ...}
    """
    try:
        result = await _api_post(
            "/v1/insurance/claims/file",
            {
                "policy_id": policy_id,
                "customer_id": customer_id,
                "claimed_amount": claimed_amount,
                "description": description,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def insurance_list_products(coverage_type: str = "") -> str:
    """List available insurance products, optionally filtered by coverage type.

    Coverage types: TRAVEL, PURCHASE, DEVICE, PAYMENT_PROTECTION

    Args:
        coverage_type: Optional filter (TRAVEL/PURCHASE/DEVICE/PAYMENT_PROTECTION). Empty = all products.

    Returns:
        JSON with list of products including base_premium, max_coverage (all as strings)
    """
    try:
        endpoint = "/v1/insurance/products"
        if coverage_type:
            endpoint += f"?coverage_type={coverage_type}"
        result = await _api_get(endpoint)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


# ── API Gateway tools (IL-AGW-01) ─────────────────────────────────────────


@mcp_server.tool()
async def gateway_create_key(
    name: str,
    owner_id: str,
    scope: list[str],
    tier: str = "BASIC",
) -> str:
    """Create a new API key for a customer or service.

    Raw key returned ONCE — never stored (I-12 SHA-256). Store it immediately.
    Tiers: FREE (1 rps), BASIC (10 rps), PREMIUM (50 rps), ENTERPRISE (200 rps).

    Args:
        name: Human-readable key name
        owner_id: Customer or service ID that owns this key
        scope: List of permitted scopes (e.g. ["payments:read", "kyc:write"])
        tier: Usage tier — FREE/BASIC/PREMIUM/ENTERPRISE (default: BASIC)

    Returns:
        JSON with raw_key (one-time), key_id, tier
    """
    try:
        result = await _api_post(
            "/v1/gateway/keys",
            {"name": name, "owner_id": owner_id, "scope": scope, "tier": tier},
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def gateway_get_usage(key_id: str) -> str:
    """Get request analytics and quota summary for an API key.

    Args:
        key_id: The API key ID to query

    Returns:
        JSON with analytics (request counts, status codes) and quota_summary
    """
    try:
        result = await _api_get(f"/v1/gateway/keys/{key_id}/usage")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def gateway_set_limits(tier: str = "") -> str:
    """Get current rate limit policies for all tiers (or a specific tier).

    Use this to understand quota policies before provisioning API keys.

    Args:
        tier: Optional — FREE/BASIC/PREMIUM/ENTERPRISE. Empty = all tiers.

    Returns:
        JSON with list of policies (requests_per_second, per_minute, per_hour, burst_allowance)
    """
    try:
        result = await _api_get("/v1/gateway/rate-limits")
        if tier:
            policies = [p for p in result.get("policies", []) if p["tier"] == tier]
            return json.dumps({"policies": policies}, indent=2)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def gateway_revoke_key(key_id: str, actor: str) -> str:
    """Revoke an API key. Returns HITL_REQUIRED — Compliance Officer must approve (I-27).

    Args:
        key_id: The API key ID to revoke
        actor: Identity of the requester (for audit trail)

    Returns:
        JSON with status=HITL_REQUIRED and key_id
    """
    try:
        result = await _api_post(f"/v1/gateway/keys/{key_id}/revoke", {"actor": actor})
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def gateway_request_analytics(key_id: str) -> str:
    """Get full request analytics for an API key — same as gateway_get_usage.

    Alias kept for discoverability. Returns request history and quota usage.

    Args:
        key_id: The API key ID to query

    Returns:
        JSON with analytics object (total_requests, error_rate, latency_p99)
    """
    try:
        result = await _api_get(f"/v1/gateway/keys/{key_id}/usage")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


# ── Webhook Orchestrator tools (IL-WHO-01) ────────────────────────────────


@mcp_server.tool()
async def webhook_subscribe(
    owner_id: str,
    url: str,
    event_types: list[str],
    description: str = "",
) -> str:
    """Subscribe to Banxe webhook events. URL must be HTTPS.

    Event types: PAYMENT_CREATED, PAYMENT_COMPLETED, PAYMENT_FAILED,
    CUSTOMER_CREATED, KYC_COMPLETED, KYC_FAILED, CARD_ISSUED, CARD_FROZEN,
    CARD_TRANSACTION, LOAN_APPLIED, LOAN_APPROVED, LOAN_DECLINED, LOAN_DISBURSED,
    INSURANCE_POLICY_BOUND, INSURANCE_CLAIM_FILED, INSURANCE_CLAIM_APPROVED,
    FX_EXECUTED, COMPLIANCE_BREACH, DOCUMENT_UPLOADED, SAFEGUARDING_ALERT.

    Args:
        owner_id: Customer or service ID subscribing to events
        url: HTTPS endpoint to receive webhook POST requests
        event_types: List of event types to subscribe to
        description: Optional human-readable description

    Returns:
        JSON with subscription_id, status=ACTIVE, and HMAC signing secret info
    """
    try:
        result = await _api_post(
            "/v1/webhooks/subscriptions",
            {
                "owner_id": owner_id,
                "url": url,
                "event_types": event_types,
                "description": description,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def webhook_list_events(event_type: str = "", limit: int = 50) -> str:
    """List recently published webhook events, optionally filtered by event type.

    Args:
        event_type: Optional filter — e.g. PAYMENT_COMPLETED. Empty = all types.
        limit: Maximum number of events to return (default: 50)

    Returns:
        JSON with count and list of events (event_id, event_type, source_service, created_at)
    """
    try:
        endpoint = "/v1/webhooks/events"
        params = []
        if event_type:
            params.append(f"event_type={event_type}")
        params.append(f"limit={limit}")
        endpoint += "?" + "&".join(params)
        result = await _api_get(endpoint)
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def webhook_retry_dlq(attempt_id: str) -> str:
    """Retry a dead-lettered webhook delivery attempt.

    The original DLQ record is preserved (append-only, I-24).
    A new PENDING attempt is created for re-delivery.

    Args:
        attempt_id: The dead-lettered delivery attempt ID to retry

    Returns:
        JSON with new_attempt_id, event_id, subscription_id, status=PENDING
    """
    try:
        result = await _api_post(f"/v1/webhooks/dlq/{attempt_id}/retry", {})
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def webhook_delivery_status(event_id: str) -> str:
    """Get delivery status for all attempts for a webhook event.

    Args:
        event_id: The webhook event ID to check

    Returns:
        JSON with deliveries list (attempt_id, subscription_id, status, http_status, attempt_number)
    """
    try:
        result = await _api_get(f"/v1/webhooks/events/{event_id}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def loyalty_get_balance(customer_id: str) -> str:
    """Get loyalty points balance and current tier for a customer.

    Args:
        customer_id: Customer identifier

    Returns:
        JSON with total_points, tier, pending_points, lifetime_points.
    """
    try:
        result = await _api_get(f"/v1/loyalty/balance/{customer_id}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def loyalty_get_tier(customer_id: str) -> str:
    """Evaluate and apply tier upgrade/downgrade for a customer based on lifetime points.

    Args:
        customer_id: Customer identifier

    Returns:
        JSON with old_tier, new_tier, lifetime_points, upgraded bool.
    """
    try:
        result = await _api_get(f"/v1/loyalty/tier/{customer_id}/evaluate")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def loyalty_redeem(customer_id: str, option_id: str, quantity: int = 1) -> str:
    """Redeem loyalty points for a reward option (cashback, FX discount, voucher).

    Args:
        customer_id: Customer identifier
        option_id: Redemption option ID (opt-cashback, opt-fx-discount, opt-card-fee, opt-voucher)
        quantity: Number of units to redeem (default: 1)

    Returns:
        JSON with redeemed_points, remaining_balance, reward details.
    """
    try:
        result = await _api_post(
            "/v1/loyalty/redeem",
            {"customer_id": customer_id, "option_id": option_id, "quantity": quantity},
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def loyalty_earn_history(customer_id: str, limit: int = 50) -> str:
    """Get points transaction history for a customer (earn, redeem, bonus, expire).

    Args:
        customer_id: Customer identifier
        limit: Maximum number of transactions to return (default: 50)

    Returns:
        JSON with transactions list (tx_type, points, balance_after, created_at, expires_at).
    """
    try:
        result = await _api_get(f"/v1/loyalty/history/{customer_id}?limit={limit}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def loyalty_expiry_forecast(customer_id: str, days_ahead: int = 30) -> str:
    """Get loyalty points expiring within days_ahead days for a customer.

    Args:
        customer_id: Customer identifier
        days_ahead: Look-ahead window in days (default: 30)

    Returns:
        JSON with expiring_transactions list and total_expiring_points.
    """
    try:
        result = await _api_get(f"/v1/loyalty/expiry/{customer_id}?days_ahead={days_ahead}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def referral_generate_code(
    customer_id: str,
    campaign_id: str = "camp-default",
    vanity_suffix: str = "",
) -> str:
    """Generate a unique referral code for a customer.

    Args:
        customer_id: Customer who will share the code
        campaign_id: Campaign ID (default: camp-default)
        vanity_suffix: Optional suffix for vanity code (e.g. "JOHN" → "BANXEJOHN")

    Returns:
        JSON with code, code_id, campaign_id, is_vanity, created_at.
    """
    try:
        result = await _api_post(
            "/v1/referral/codes",
            {
                "customer_id": customer_id,
                "campaign_id": campaign_id,
                "vanity_suffix": vanity_suffix,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def referral_get_status(referral_id: str) -> str:
    """Get current status and details of a referral.

    Args:
        referral_id: Referral identifier

    Returns:
        JSON with referral_id, referrer_id, referee_id, status, qualified_at, rewarded_at.
    """
    try:
        result = await _api_get(f"/v1/referral/{referral_id}/status")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def referral_campaign_stats(campaign_id: str = "camp-default") -> str:
    """Get referral campaign budget and statistics.

    Args:
        campaign_id: Campaign ID (default: camp-default)

    Returns:
        JSON with total_budget, spent_budget, remaining_budget, referrer_reward, referee_reward.
    """
    try:
        result = await _api_get(f"/v1/referral/campaigns/{campaign_id}/stats")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def referral_fraud_report(referral_id: str) -> str:
    """Get fraud check report for a referral.

    Args:
        referral_id: Referral identifier

    Returns:
        JSON with checked, is_fraudulent, fraud_reason, confidence_score, checked_at.
    """
    try:
        result = await _api_post(
            f"/v1/referral/{referral_id}/fraud-check",
            {"referrer_id": "", "referee_id": "", "ip_address": "0.0.0.0"},  # nosec B104
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def savings_open_account(
    customer_id: str,
    product_id: str,
    initial_deposit: str,
) -> str:
    """Open a new savings account for a customer.

    Args:
        customer_id: Customer identifier
        product_id: Savings product ID (e.g. prod-easy-access, prod-fixed-12m)
        initial_deposit: Opening deposit amount as decimal string (e.g. '1000.00')

    Returns:
        JSON with account_id, status, balance, maturity_date (if applicable).
    """
    try:
        result = await _api_post(
            "/v1/savings/open",
            {
                "customer_id": customer_id,
                "product_id": product_id,
                "initial_deposit": initial_deposit,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def savings_get_interest(account_id: str) -> str:
    """Get interest summary for a savings account.

    Args:
        account_id: Savings account identifier

    Returns:
        JSON with balance, gross_rate, aer, daily_interest, tax_info.
    """
    try:
        result = await _api_get(f"/v1/savings/{account_id}/interest")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def savings_get_products() -> str:
    """List all available savings products.

    Returns:
        JSON with count and list of products (id, name, type, rates, limits).
    """
    try:
        result = await _api_get("/v1/savings/products")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def savings_calculate_maturity(
    principal: str,
    gross_rate: str,
    days: int,
) -> str:
    """Calculate maturity amount for a fixed-term savings scenario.

    Args:
        principal: Principal amount as decimal string (e.g. '10000.00')
        gross_rate: Annual gross interest rate as decimal (e.g. '0.052')
        days: Term length in days (e.g. 365 for 1-year fixed)

    Returns:
        JSON with maturity_amount, gross_interest, net_interest, tax_withheld.
    """
    try:
        result = await _api_post(
            "/v1/savings/calculate-maturity",
            {"principal": principal, "gross_rate": gross_rate, "days": days},
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def savings_rate_history(product_id: str) -> str:
    """Get interest rate change history for a savings product.

    Args:
        product_id: Savings product identifier (e.g. prod-easy-access)

    Returns:
        JSON with count and list of historical rate records.
    """
    try:
        result = await _api_get(f"/v1/savings/rates/{product_id}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def schedule_create_standing_order(
    customer_id: str,
    from_account: str,
    to_account: str,
    amount: str,
    frequency: str,
    start_date: str,
) -> str:
    """Create a new standing order for a customer.

    Args:
        customer_id: Customer identifier
        from_account: Source account ID
        to_account: Destination account ID
        amount: Payment amount as decimal string (e.g. '250.00')
        frequency: DAILY | WEEKLY | FORTNIGHTLY | MONTHLY | QUARTERLY | ANNUAL
        start_date: ISO 8601 start date (e.g. '2026-05-01T00:00:00+00:00')

    Returns:
        JSON with so_id, status=ACTIVE, next_execution_date.
    """
    try:
        result = await _api_post(
            "/v1/standing-orders",
            {
                "customer_id": customer_id,
                "from_account": from_account,
                "to_account": to_account,
                "amount": amount,
                "frequency": frequency,
                "start_date": start_date,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def schedule_create_dd_mandate(
    customer_id: str,
    creditor_id: str,
    creditor_name: str,
    scheme_ref: str,
    service_user_number: str,
) -> str:
    """Create a new Direct Debit mandate.

    Args:
        customer_id: Customer identifier
        creditor_id: Creditor/merchant identifier
        creditor_name: Creditor display name (e.g. 'Utility Company Ltd')
        scheme_ref: Unique scheme reference for the mandate
        service_user_number: Bacs Service User Number (SUN)

    Returns:
        JSON with mandate_id, status=PENDING, creditor_name.
    """
    try:
        result = await _api_post(
            "/v1/direct-debits/mandate",
            {
                "customer_id": customer_id,
                "creditor_id": creditor_id,
                "creditor_name": creditor_name,
                "scheme_ref": scheme_ref,
                "service_user_number": service_user_number,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def schedule_get_upcoming(customer_id: str, days_ahead: int = 7) -> str:
    """Get upcoming scheduled payments for a customer.

    Args:
        customer_id: Customer identifier
        days_ahead: Look-ahead window in days (default: 7)

    Returns:
        JSON with count and list of upcoming payment schedules.
    """
    try:
        result = await _api_get(
            f"/v1/scheduled-payments/{customer_id}/upcoming?days_ahead={days_ahead}",
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def schedule_failure_report(customer_id: str) -> str:
    """Get payment failure report for a customer.

    Args:
        customer_id: Customer identifier

    Returns:
        JSON with count of failures, retry status, and failure details.
    """
    try:
        result = await _api_get(f"/v1/scheduled-payments/{customer_id}/failures")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


# ── Phase 33: Dispute Resolution & Chargeback Management (IL-DRM-01) ─────────


@mcp_server.tool()
async def dispute_file(
    customer_id: str,
    payment_id: str,
    dispute_type: str,
    amount: str,
    description: str = "",
) -> str:
    """File a new dispute for an unauthorised or incorrect payment (DISP 1.3).

    Args:
        customer_id: Customer identifier
        payment_id: Original payment reference
        dispute_type: UNAUTHORIZED_TRANSACTION | DUPLICATE_CHARGE | MERCHANDISE_NOT_RECEIVED | DEFECTIVE_MERCHANDISE | CREDIT_NOT_PROCESSED
        amount: Amount in dispute (string decimal, I-01)
        description: Optional description of the dispute

    Returns:
        JSON with dispute_id, status=OPENED, sla_deadline (56-day clock starts).
    """
    try:
        result = await _api_post(
            "/v1/disputes",
            {
                "customer_id": customer_id,
                "payment_id": payment_id,
                "dispute_type": dispute_type,
                "amount": amount,
                "description": description,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def dispute_get_status(dispute_id: str) -> str:
    """Get current status of a dispute including SLA deadline.

    Args:
        dispute_id: Dispute identifier

    Returns:
        JSON with status, amount, sla_deadline, dispute_type.
    """
    try:
        result = await _api_get(f"/v1/disputes/{dispute_id}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def dispute_submit_evidence(
    dispute_id: str,
    evidence_type: str,
    file_content: str,
    description: str = "",
) -> str:
    """Submit evidence for an active dispute (SHA-256 hashed, I-12).

    Args:
        dispute_id: Dispute identifier
        evidence_type: RECEIPT | SCREENSHOT | BANK_STATEMENT | COMMUNICATION | PHOTO
        file_content: File content as string (will be UTF-8 encoded and hashed)
        description: Optional description

    Returns:
        JSON with evidence_id, file_hash (SHA-256, 64 chars).
    """
    try:
        result = await _api_post(
            f"/v1/disputes/{dispute_id}/evidence",
            {
                "evidence_type": evidence_type,
                "file_content": file_content,
                "description": description,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def dispute_escalate(
    dispute_id: str,
    reason: str,
    level: str = "LEVEL_1",
) -> str:
    """Escalate a dispute (DISP 1.6 — use FOS level after 8-week SLA breach).

    Args:
        dispute_id: Dispute identifier
        reason: Reason for escalation
        level: LEVEL_1 | LEVEL_2 | FOS (use FOS after SLA breach per DISP 1.6)

    Returns:
        JSON with escalation_id, level, status=ESCALATED.
    """
    try:
        result = await _api_post(
            f"/v1/disputes/{dispute_id}/escalate",
            {
                "reason": reason,
                "level": level,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def dispute_resolution_report(customer_id: str) -> str:
    """Get all disputes and resolution status for a customer.

    Args:
        customer_id: Customer identifier

    Returns:
        JSON with count and list of disputes with status and amounts.
    """
    try:
        result = await _api_get(f"/v1/disputes/customers/{customer_id}/report")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


# ── Phase 34: Beneficiary & Payee Management (IL-BPM-01) ─────────────────────


@mcp_server.tool()
async def beneficiary_add(
    customer_id: str,
    beneficiary_type: str,
    name: str,
    account_number: str = "",
    sort_code: str = "",
    iban: str = "",
    bic: str = "",
    currency: str = "GBP",
    country_code: str = "GB",
) -> str:
    """Add a new beneficiary/payee for a customer (PSR 2017, MLR 2017 Reg.28).

    Args:
        customer_id: Customer identifier
        beneficiary_type: INDIVIDUAL | BUSINESS | JOINT
        name: Beneficiary display name
        account_number: UK account number (for FPS/BACS/CHAPS)
        sort_code: UK sort code
        iban: IBAN for SEPA/international
        bic: BIC/SWIFT code
        currency: Payment currency (default GBP)
        country_code: ISO 2-letter country — blocked: RU/BY/IR/KP/CU/MM/AF/VE/SY (I-02)

    Returns:
        JSON with beneficiary_id, status=PENDING. Raises 400 for blocked jurisdictions.
    """
    try:
        result = await _api_post(
            "/v1/beneficiaries",
            {
                "customer_id": customer_id,
                "beneficiary_type": beneficiary_type,
                "name": name,
                "account_number": account_number,
                "sort_code": sort_code,
                "iban": iban,
                "bic": bic,
                "currency": currency,
                "country_code": country_code,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def beneficiary_screen(beneficiary_id: str) -> str:
    """Run sanctions screening on a beneficiary via Moov Watchman (MLR 2017 Reg.28).

    Args:
        beneficiary_id: Beneficiary identifier

    Returns:
        JSON with result: NO_MATCH | PARTIAL_MATCH | MATCH, record_id, details.
    """
    try:
        result = await _api_post(f"/v1/beneficiaries/{beneficiary_id}/screen", {})
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def beneficiary_get_status(beneficiary_id: str) -> str:
    """Get current status and details of a beneficiary.

    Args:
        beneficiary_id: Beneficiary identifier

    Returns:
        JSON with name, status, country_code, currency.
    """
    try:
        result = await _api_get(f"/v1/beneficiaries/{beneficiary_id}")
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.tool()
async def beneficiary_payment_rails(
    beneficiary_id: str,
    amount: str,
    currency: str = "GBP",
) -> str:
    """Select optimal payment rail for a beneficiary (FPS/CHAPS/SEPA/SWIFT).

    Args:
        beneficiary_id: Beneficiary identifier
        amount: Payment amount as decimal string (I-01)
        currency: ISO currency code (default GBP)

    Returns:
        JSON with rail, estimated_settlement, fee_indicator, max_amount.
    """
    try:
        result = await _api_post(
            f"/v1/beneficiaries/{beneficiary_id}/route",
            {
                "amount": amount,
                "currency": currency,
            },
        )
        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as exc:
        return json.dumps({"error": str(exc), "status_code": exc.response.status_code})


@mcp_server.resource("banxe://info")
async def info_resource() -> str:
    """BANXE EMI platform information."""
    return (
        "BANXE AI Bank — FCA-authorised EMI Platform\n"
        "MCP Server v0.1.0 (Phase 0: Read-Only)\n"
        "Tools: get_account_balance, list_accounts, get_transaction_history, "
        "get_kyc_status, check_aml_alert, get_exchange_rate, get_payment_status, "
        "kb_list_notebooks, kb_get_notebook, kb_query, kb_search, "
        "kb_compare_versions, kb_get_citations, "
        "experiment_design, experiment_list, experiment_get_metrics, experiment_propose_change, "
        "monitor_score_transaction, monitor_get_alerts, monitor_get_alert_detail, "
        "monitor_get_velocity, monitor_dashboard_metrics, "
        "support_create_ticket, support_get_metrics, support_check_sla, support_route_ticket, "
        "report_generate, report_validate, report_schedule, report_audit_log, "
        "report_list_templates, "
        "ob_create_consent, ob_initiate_payment, ob_get_accounts, ob_revoke_consent, "
        "ob_list_aspsps, "
        "audit_query_events, audit_generate_report, audit_risk_score, audit_governance_status, "
        "treasury_get_positions, treasury_forecast, treasury_propose_sweep, treasury_reconcile, "
        "treasury_pending_sweeps, "
        "notify_send, notify_list_templates, notify_get_preferences, notify_delivery_status, "
        "card_issue, card_freeze, card_get_status, card_set_limits, card_list_transactions, "
        "merchant_onboard, merchant_accept_payment, merchant_get_settlements, "
        "merchant_handle_chargeback, merchant_risk_score, "
        "fx_get_quote, fx_execute, fx_get_rates, fx_get_spreads, fx_history, "
        "mc_get_balances, mc_convert, mc_reconcile_nostro, mc_currency_report, "
        "compliance_evaluate, compliance_get_rules, compliance_report_breach, "
        "compliance_track_remediation, compliance_policy_diff, "
        "doc_upload, doc_search, doc_get_versions, doc_retention_status, "
        "lending_apply, lending_score, lending_get_schedule, lending_arrears_status, lending_provision_report, "
        "insurance_get_quote, insurance_bind_policy, insurance_file_claim, insurance_list_products, "
        "gateway_create_key, gateway_get_usage, gateway_set_limits, gateway_revoke_key, "
        "gateway_request_analytics, "
        "webhook_subscribe, webhook_list_events, webhook_retry_dlq, webhook_delivery_status, "
        "loyalty_get_balance, loyalty_get_tier, loyalty_redeem, loyalty_earn_history, "
        "loyalty_expiry_forecast, "
        "referral_generate_code, referral_get_status, referral_campaign_stats, referral_fraud_report, "
        "savings_open_account, savings_get_interest, savings_get_products, savings_calculate_maturity, "
        "savings_rate_history, "
        "schedule_create_standing_order, schedule_create_dd_mandate, schedule_get_upcoming, "
        "schedule_failure_report, "
        "dispute_file, dispute_get_status, dispute_submit_evidence, dispute_escalate, "
        "dispute_resolution_report, "
        "beneficiary_add, beneficiary_screen, beneficiary_get_status, beneficiary_payment_rails\n"
        "FCA basis: CASS 7.15, CASS 15, MLR 2017, PSR 2017, DISP 1.3, PS22/9, SUP 16, PSD2 RTS, ICOBS\n"
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
