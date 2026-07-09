"""Sprint 3 Docker Port — container monitoring and control via Docker API.

Protocol DI pattern: DockerPort interface with HttpDockerPort and InMemoryDockerPort.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class ContainerStatus:
    """Docker container status snapshot."""

    name: str
    state: str  # running, exited, restarting, etc.
    exit_code: int
    restart_count: int
    health: str | None  # healthy, unhealthy, None


class DockerPort(Protocol):
    """Protocol for Docker container operations."""

    async def list_containers(self) -> list[ContainerStatus]:
        """List all containers (running and exited)."""
        ...

    async def start_container(self, name: str) -> bool:
        """Start a container by name. Only safe if exit_code==0 (clean stop)."""
        ...


class HttpDockerPort:
    """Live Docker adapter via Unix socket at /var/run/docker.sock."""

    def __init__(self, socket_path: str = "/var/run/docker.sock") -> None:
        self._socket_path = socket_path

    async def list_containers(self) -> list[ContainerStatus]:
        """List all containers using Docker API v1.41.

        GET /v1.41/containers/json?all=1
        """
        try:
            transport = httpx.AsyncHTTPTransport(uds=self._socket_path)
            async with httpx.AsyncClient(transport=transport) as client:
                resp = await client.get(
                    "http+unix://localhost/v1.41/containers/json?all=1",
                    timeout=10.0,
                )
                resp.raise_for_status()
                containers = resp.json()

            result: list[ContainerStatus] = []
            for c in containers:
                state = c.get("State", "unknown")
                exit_code = c.get("ExitCode", -1)
                restart_count = c.get("RestartCount", 0)
                health_status: str | None = None
                if "HealthCheck" in c.get("Config", {}):
                    health_status = c.get("Health", {}).get("Status")

                result.append(
                    ContainerStatus(
                        name=c["Names"][0].lstrip("/") if c.get("Names") else "unknown",
                        state=state,
                        exit_code=exit_code,
                        restart_count=restart_count,
                        health=health_status,
                    )
                )
            return result
        except Exception:
            return []

    async def start_container(self, name: str) -> bool:
        """Start a container by name using Docker API v1.41.

        POST /v1.41/containers/{name}/start

        Safety: only start if container status shows exit_code==0 (clean stop).
        Never auto-start if exit_code != 0 or restart_count > crash_loop_threshold.
        """
        try:
            # First, verify container is in a safe state
            containers = await self.list_containers()
            target = next((c for c in containers if c.name == name), None)
            if target is None:
                return False

            # Only safe to start if clean exit (exit_code=0) and not crash-loop
            if not self._safe_to_start(target):
                return False

            transport = httpx.AsyncHTTPTransport(uds=self._socket_path)
            async with httpx.AsyncClient(transport=transport) as client:
                resp = await client.post(
                    f"http+unix://localhost/v1.41/containers/{name}/start",
                    timeout=10.0,
                )
                return resp.status_code in (204, 304)  # 204 = started, 304 = already running
        except Exception:
            return False

    @staticmethod
    def _safe_to_start(container: ContainerStatus) -> bool:
        """Check if container is safe to auto-start.

        Safe = clean stop (exit_code == 0) AND not in crash-loop (restart_count <= 10).
        """
        if container.exit_code != 0:
            return False
        if container.restart_count > 10:
            return False
        return True


class InMemoryDockerPort:
    """Stub Docker adapter for unit tests."""

    def __init__(
        self,
        containers: list[ContainerStatus] | None = None,
        start_result: bool = True,
    ) -> None:
        self._containers = containers or []
        self._start_result = start_result

    async def list_containers(self) -> list[ContainerStatus]:
        """Return pre-configured containers."""
        return list(self._containers)

    async def start_container(self, name: str) -> bool:
        """Return pre-configured result."""
        container = next((c for c in self._containers if c.name == name), None)
        if container is None:
            return False
        # Check safety
        if container.exit_code != 0 or container.restart_count > 10:
            return False
        return self._start_result

    def update_containers(self, containers: list[ContainerStatus]) -> None:
        """Update container list (for testing state changes)."""
        self._containers = containers
