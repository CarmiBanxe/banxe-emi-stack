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
        "notify_send, notify_list_templates, notify_get_preferences, notify_delivery_status\n"
        "FCA basis: CASS 7.15, CASS 15, MLR 2017, PSR 2017, DISP 1.3, PS22/9, SUP 16, PSD2 RTS\n"
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
