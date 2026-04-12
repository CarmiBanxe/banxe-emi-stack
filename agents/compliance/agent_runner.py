"""
agents/compliance/agent_runner.py — Individual agent runtime.
Loads soul file as system prompt, executes tools, respects autonomy levels.
IL-068 | banxe-emi-stack

Autonomy Levels (from swarm.yaml):
  L1: Human does everything, agent only suggests
  L2: Agent acts, but HITL gates block critical decisions
  L3: Agent acts autonomously within defined thresholds
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import logging
from pathlib import Path
from typing import Any
import uuid

from agents.compliance.tools import ToolCallable, resolve_tools

logger = logging.getLogger("banxe.swarm.agent")


class AutonomyLevel(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_HITL = "waiting_hitl"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class AgentConfig:
    """Parsed from swarm.yaml agent entry."""

    id: str
    soul_path: str
    autonomy: AutonomyLevel
    human_double: str
    depends_on: list[str] = field(default_factory=list)
    parallel: bool = False
    tool_names: list[str] = field(default_factory=list)
    thresholds: dict[str, Any] = field(default_factory=dict)
    hitl_gates: list[str] = field(default_factory=list)
    sla_ms: int | None = None


@dataclass
class AgentEvent:
    """Audit event emitted by an agent."""

    event_id: str
    agent_id: str
    event_type: str
    timestamp: str
    payload: dict[str, Any] = field(default_factory=dict)


class ComplianceAgent:
    """
    Runtime for a single compliance agent.
    Loads soul (system prompt), resolves tools, processes events.
    """

    def __init__(self, config: AgentConfig, swarm_root: Path) -> None:
        self.config = config
        self.status = AgentStatus.IDLE
        self.soul_text: str = ""
        self.tools: dict[str, ToolCallable] = {}
        self.event_log: list[AgentEvent] = []
        self._swarm_root = swarm_root
        self._load_soul()
        self._resolve_tools()

    def _load_soul(self) -> None:
        soul_path = self._swarm_root / self.config.soul_path
        if soul_path.exists():
            self.soul_text = soul_path.read_text(encoding="utf-8")
            logger.info("Agent %s: soul loaded (%d chars)", self.config.id, len(self.soul_text))
        else:
            logger.warning("Agent %s: soul file not found: %s", self.config.id, soul_path)

    def _resolve_tools(self) -> None:
        self.tools = resolve_tools(self.config.tool_names)
        missing = set(self.config.tool_names) - set(self.tools.keys())
        if missing:
            logger.warning("Agent %s: unresolved tools: %s", self.config.id, missing)

    def _emit_event(self, event_type: str, payload: dict[str, Any] | None = None) -> AgentEvent:
        evt = AgentEvent(
            event_id=str(uuid.uuid4()),
            agent_id=self.config.id,
            event_type=event_type,
            timestamp=datetime.now(UTC).isoformat(),
            payload=payload or {},
        )
        self.event_log.append(evt)
        return evt

    async def _call_tool(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        if tool_name not in self.tools:
            raise ValueError(f"Tool {tool_name} not available for agent {self.config.id}")
        kwargs["agent_id"] = self.config.id
        result = await self.tools[tool_name](**kwargs)
        self._emit_event(
            f"tool.{tool_name}", {"kwargs": str(kwargs)[:200], "result": str(result)[:200]}
        )
        return result

    async def _check_hitl_gate(self, gate_name: str, case_id: str) -> dict[str, Any]:
        if self.config.autonomy == AutonomyLevel.L3:
            logger.info("Agent %s: L3 autonomy, skipping HITL gate %s", self.config.id, gate_name)
            return {"status": "auto_approved", "gate": gate_name}
        return await self._call_tool("hitl_check_gate", gate_name=gate_name, case_id=case_id)

    async def start(self) -> None:
        self.status = AgentStatus.RUNNING
        self._emit_event("agent.started")
        await self._call_tool(
            "clickhouse_log_event",
            event_type="agent.started",
            payload={"soul_chars": len(self.soul_text)},
        )
        logger.info(
            "Agent %s STARTED (autonomy=%s, tools=%d)",
            self.config.id,
            self.config.autonomy.value,
            len(self.tools),
        )

    async def stop(self) -> None:
        self.status = AgentStatus.STOPPED
        self._emit_event("agent.stopped")
        logger.info("Agent %s STOPPED (events=%d)", self.config.id, len(self.event_log))

    async def process_event(self, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        self._emit_event(f"process.{event_type}", data)
        logger.info("Agent %s processing: %s", self.config.id, event_type)
        return {"agent_id": self.config.id, "event_type": event_type, "status": "processed"}

    def info(self) -> dict[str, Any]:
        return {
            "id": self.config.id,
            "autonomy": self.config.autonomy.value,
            "human_double": self.config.human_double,
            "status": self.status.value,
            "tools": list(self.tools.keys()),
            "soul_loaded": bool(self.soul_text),
            "events_count": len(self.event_log),
        }
