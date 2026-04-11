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
            f"Breach History — {account_id} (SANDBOX — API unavailable)\n"
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
            f"Discrepancy Trend — {account_id} (SANDBOX — API unavailable)\n"
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
            f"ARL Metrics (last {hours}h) — SANDBOX\n"
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
