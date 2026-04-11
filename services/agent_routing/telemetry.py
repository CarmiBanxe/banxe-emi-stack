"""
services/agent_routing/telemetry.py — ARL Telemetry
IL-ARL-01 | banxe-emi-stack

Emits routing metrics to ClickHouse for cost visibility and monitoring.
Metrics: tokens, latency, tier distribution, decision ratios, reuse rate.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ── ClickHouse Port ───────────────────────────────────────────────────────────


class ClickHousePort(Protocol):
    """Port for ClickHouse writes — append-only metrics store (I-24)."""

    async def insert(self, table: str, rows: list[dict[str, Any]]) -> None: ...


class InMemoryClickHouse:
    """In-memory ClickHouse stub for tests and local development."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def insert(self, table: str, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            self.rows.append({"table": table, **row})


# ── Routing Event Schema ──────────────────────────────────────────────────────


_TABLE = "agent_routing_events"

# ClickHouse CREATE TABLE (for reference — applied via migration):
# CREATE TABLE agent_routing_events (
#   event_time   DateTime64(3, 'UTC'),
#   task_id      String,
#   tier         UInt8,
#   event_type   LowCardinality(String),
#   product      LowCardinality(String),
#   jurisdiction LowCardinality(String),
#   tokens_input UInt32,
#   tokens_output UInt32,
#   latency_ms   UInt32,
#   decision     LowCardinality(String),
#   reasoning_reused UInt8,
#   cost_usd     Float32
# ) ENGINE = MergeTree()
# PARTITION BY toYYYYMM(event_time)
# ORDER BY (event_time, tier, product)
# TTL event_time + INTERVAL 5 YEAR;  -- I-08


# ── ARL Telemetry Service ─────────────────────────────────────────────────────


class ARLTelemetry:
    """Emits agent routing metrics to ClickHouse.

    Cost model (approximate USD per 1k tokens):
      Tier 1: $0.000 (rule engine)
      Tier 2: $0.025 (Haiku-class)
      Tier 3: $0.150 (Opus-class)
    """

    _COST_PER_1K_TOKENS: dict[int, float] = {
        1: 0.000,
        2: 0.025,
        3: 0.150,
    }

    def __init__(self, clickhouse: ClickHousePort | None = None) -> None:
        self._ch: ClickHousePort = clickhouse or InMemoryClickHouse()

    async def emit_routing_event(
        self,
        task_id: str,
        tier: int,
        event_type: str,
        product: str,
        jurisdiction: str,
        total_tokens: int,
        latency_ms: int,
        decision: str,
        reasoning_reused: bool,
        tokens_input: int = 0,
        tokens_output: int = 0,
    ) -> None:
        """Emit a single routing event to ClickHouse."""
        cost_usd = (total_tokens / 1000) * self._COST_PER_1K_TOKENS.get(tier, 0.15)
        row = {
            "event_time": datetime.now(UTC).isoformat(),
            "task_id": task_id,
            "tier": tier,
            "event_type": event_type,
            "product": product,
            "jurisdiction": jurisdiction,
            "tokens_input": tokens_input or (total_tokens // 2),
            "tokens_output": tokens_output or (total_tokens - tokens_input or total_tokens // 2),
            "latency_ms": latency_ms,
            "decision": decision,
            "reasoning_reused": int(reasoning_reused),
            "cost_usd": round(cost_usd, 6),
        }
        try:
            await self._ch.insert(_TABLE, [row])
        except Exception:
            logger.exception("Failed to emit routing telemetry for task %s", task_id)

    async def emit_agent_response(
        self,
        task_id: str,
        agent_name: str,
        signal_type: str,
        risk_score: float,
        confidence: float,
        decision_hint: str,
        token_cost: int,
        latency_ms: int,
    ) -> None:
        """Emit per-agent response metrics."""
        row = {
            "event_time": datetime.now(UTC).isoformat(),
            "task_id": task_id,
            "agent_name": agent_name,
            "signal_type": signal_type,
            "risk_score": risk_score,
            "confidence": confidence,
            "decision_hint": decision_hint,
            "token_cost": token_cost,
            "latency_ms": latency_ms,
        }
        try:
            await self._ch.insert("agent_response_events", [row])
        except Exception:
            logger.exception("Failed to emit agent response telemetry for task %s", task_id)

    def compute_cost_usd(self, tier: int, total_tokens: int) -> float:
        """Compute estimated USD cost for a tier+token combination."""
        return round((total_tokens / 1000) * self._COST_PER_1K_TOKENS.get(tier, 0.15), 6)
