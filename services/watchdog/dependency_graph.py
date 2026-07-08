"""Sprint 3+ Watchdog Dependency Graph — topology context for cascade detection.

Maps service dependencies so that an incident on a dependent service can be
marked as upstream cascade when the upstream is already unhealthy. Suppresses
duplicate ESCALATE noise from a single root failure propagating through the graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class DependencyGraphPort(Protocol):
    """Protocol for dependency topology queries."""

    def get_dependencies(self, target: str) -> list[str]: ...

    def is_cascade(self, target: str, unhealthy_set: frozenset[str]) -> bool: ...

    def upstream_cause(self, target: str, unhealthy_set: frozenset[str]) -> str | None: ...


@dataclass
class DependencyGraph:
    """In-memory directed dependency graph: service -> upstream services it depends on.

    Protocol-compatible with DependencyGraphPort.

    YAML format consumed by from_dict::

        dependency_graph:
          intent-dispatcher:
            depends_on:
              - litellm-postgres
    """

    _deps: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict) -> DependencyGraph:
        """Build from the dependency_graph YAML section (dict of service configs)."""
        graph = cls()
        for service, config in (raw or {}).items():
            depends_on: list[str] = (config or {}).get("depends_on") or []
            graph._deps[service] = list(depends_on)
        return graph

    def get_dependencies(self, target: str) -> list[str]:
        """Return the list of upstream services that target depends on."""
        return list(self._deps.get(target, []))

    def is_cascade(self, target: str, unhealthy_set: frozenset[str]) -> bool:
        """True if any upstream dep of target is currently unhealthy."""
        return any(dep in unhealthy_set for dep in self._deps.get(target, []))

    def upstream_cause(self, target: str, unhealthy_set: frozenset[str]) -> str | None:
        """Return the first unhealthy upstream dep name, or None."""
        for dep in self._deps.get(target, []):
            if dep in unhealthy_set:
                return dep
        return None


class InMemoryDependencyGraph:
    """Stub dependency graph for unit tests."""

    def __init__(self, deps: dict[str, list[str]] | None = None) -> None:
        self._deps: dict[str, list[str]] = deps or {}

    def get_dependencies(self, target: str) -> list[str]:
        return list(self._deps.get(target, []))

    def is_cascade(self, target: str, unhealthy_set: frozenset[str]) -> bool:
        return any(dep in unhealthy_set for dep in self._deps.get(target, []))

    def upstream_cause(self, target: str, unhealthy_set: frozenset[str]) -> str | None:
        for dep in self._deps.get(target, []):
            if dep in unhealthy_set:
                return dep
        return None
