"""Kill switch (ADR-030 §9). A RED agent's decision path MUST call ``assert_can_act``
before acting; a HALTED agent — or an unreachable backend — refuses (fail-closed).

InMemory is the sandbox default. Temporal is the production adapter (Outcome-C stub).
"""

from __future__ import annotations

from typing import Protocol

from .errors import AgentHalted


class KillSwitchPort(Protocol):
    """DI seam."""

    def terminate(self, agent_id: str, reason: str) -> None: ...
    def is_halted(self, agent_id: str) -> bool: ...
    def status(self) -> dict[str, str]: ...


class InMemoryKillSwitch:
    """Sandbox default — deterministic, no external dependency."""

    def __init__(self) -> None:
        self._halted: dict[str, str] = {}

    def terminate(self, agent_id: str, reason: str) -> None:
        self._halted[agent_id] = reason

    def resume(self, agent_id: str) -> None:  # operator-only, sandbox convenience
        self._halted.pop(agent_id, None)

    def is_halted(self, agent_id: str) -> bool:
        return agent_id in self._halted

    def status(self) -> dict[str, str]:
        return dict(self._halted)


class TemporalKillSwitch:
    """Production adapter (Outcome-C). Terminates the agent's Temporal workflow."""

    def terminate(self, agent_id: str, reason: str) -> None:
        raise NotImplementedError(
            "Outcome-C: wire Temporal `WorkflowHandle.terminate(reason)` here.")

    def is_halted(self, agent_id: str) -> bool:
        raise NotImplementedError("Outcome-C: query Temporal workflow status.")

    def status(self) -> dict[str, str]:
        raise NotImplementedError("Outcome-C: list terminated workflows.")


def assert_can_act(kill_switch: KillSwitchPort, agent_id: str) -> None:
    """Fail-closed gate. HALTED, or an unreachable backend, ⇒ AgentHalted (refuse).

    'Allow' requires a positive, reachable ``is_halted == False``. Absence of a
    reachable answer is treated as HALTED (deny-by-default)."""
    try:
        halted = kill_switch.is_halted(agent_id)
    except Exception as exc:  # backend unavailable ⇒ fail-closed HALTED
        raise AgentHalted(
            f"kill-switch backend unavailable ⇒ {agent_id} treated HALTED "
            f"(deny-by-default): {exc!r}") from exc
    if halted:
        raise AgentHalted(f"{agent_id} is HALTED — decision path refuses to act")
