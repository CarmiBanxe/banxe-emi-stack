"""
services/swarm/agents/base_agent.py — BaseAgent ABC
IL-ARL-01 | banxe-emi-stack

Unified interface all specialized swarm agents must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from services.agent_routing.models import AgentTask
from services.agent_routing.schemas import AgentResponse


class BaseAgent(ABC):
    """Abstract base for all swarm compliance agents.

    Each agent implements `analyze()` and exposes `agent_name` and `signal_type`.
    All agents return a unified `AgentResponse` — no agent-specific response types.
    """

    @abstractmethod
    async def analyze(self, task: AgentTask) -> AgentResponse:
        """Analyze the task and return a compliance signal.

        Args:
            task: The normalized AgentTask envelope.

        Returns:
            AgentResponse with risk_score, confidence, decision_hint, and evidence.
        """
        ...

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Unique agent identifier used in AgentResponse.agent_name."""
        ...

    @property
    @abstractmethod
    def signal_type(self) -> str:
        """The compliance signal this agent assesses (e.g. 'sanctions_screening')."""
        ...
