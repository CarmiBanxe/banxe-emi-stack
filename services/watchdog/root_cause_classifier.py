"""Sprint 3+ Root Cause Classifier — diagnose infra incidents from logs/status/context.

Normalised reason codes + confidence from raw logs, container state, and context dict.
No external ML dependencies — keyword pattern matching only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RootCause(str, Enum):
    AUTH_FAILURE = "AUTH_FAILURE"
    CRASH_LOOP = "CRASH_LOOP"
    EXITED_ZERO = "EXITED_ZERO"
    OOM_KILLED = "OOM_KILLED"
    PORT_BIND_FAILURE = "PORT_BIND_FAILURE"
    HEALTHCHECK_MISCONFIG = "HEALTHCHECK_MISCONFIG"
    NODE_OFFLINE = "NODE_OFFLINE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Classification:
    """Result of root cause classification."""

    reason: RootCause
    confidence: float  # 0.0–1.0
    evidence: list[str] = field(default_factory=list)  # matching snippets


# Ordered by specificity — most specific first
_LOG_PATTERNS: list[tuple[RootCause, list[str]]] = [
    (
        RootCause.OOM_KILLED,
        ["out of memory", "oom killer", "killed process", "memory limit exceeded", "cannot allocate memory"],
    ),
    (
        RootCause.AUTH_FAILURE,
        ["authentication failed", "access denied", "invalid credentials", "unauthorized", "permission denied"],
    ),
    (
        RootCause.PORT_BIND_FAILURE,
        ["address already in use", "port already in use", "eaddrinuse", "bind: address"],
    ),
    (
        RootCause.HEALTHCHECK_MISCONFIG,
        ["health check failed", "healthcheck failed", "no healthcheck defined"],
    ),
    (
        RootCause.NODE_OFFLINE,
        ["connection refused", "no route to host", "network unreachable", "connection timed out"],
    ),
]

# 137 = 128 + SIGKILL(9) — standard OOM-kill exit code
_OOM_EXIT_CODES: frozenset[int] = frozenset({137})


class RootCauseClassifier:
    """Classify infra failures into normalised reason codes.

    Priority order:
    1. restart_count > crash_loop_threshold → CRASH_LOOP (0.95)
    2. exit_code in OOM set → OOM_KILLED (0.80)
    3. exit_code == 0 and state == "exited" → EXITED_ZERO (1.0)
    4. log keyword match → specific code (0.75–0.90)
    5. state == "restarting" → CRASH_LOOP (0.70)
    6. state in {"dead","removing"} or context.node_offline → NODE_OFFLINE (0.65)
    7. fallback → UNKNOWN (0.30)
    """

    def classify(
        self,
        logs: list[str] | None = None,
        state: str = "",
        exit_code: int = 0,
        restart_count: int = 0,
        crash_loop_threshold: int = 10,
        context: dict | None = None,
    ) -> Classification:
        """Classify an infra incident.

        Args:
            logs: raw log lines from container/node
            state: container state string (running, exited, restarting, …)
            exit_code: container exit code (0 = clean stop)
            restart_count: restarts since container creation
            crash_loop_threshold: restarts above which crash-loop is declared
            context: optional extra context

        Returns:
            Classification with reason, confidence, and evidence list.
        """
        raw = [line.lower() for line in (logs or [])]

        # Rule 1 — crash-loop by restart count
        if restart_count > crash_loop_threshold:
            return Classification(
                reason=RootCause.CRASH_LOOP,
                confidence=0.95,
                evidence=[f"restart_count={restart_count} > threshold={crash_loop_threshold}"],
            )

        # Rule 2 — OOM exit code
        if exit_code in _OOM_EXIT_CODES:
            evidence: list[str] = [f"exit_code={exit_code} (OOM kill)"]
            for line in raw:
                if any(kw in line for kw in ["out of memory", "oom", "memory"]):
                    evidence.append(line[:120])
                    break
            return Classification(reason=RootCause.OOM_KILLED, confidence=0.80, evidence=evidence)

        # Rule 3 — clean exit
        if exit_code == 0 and state == "exited":
            return Classification(
                reason=RootCause.EXITED_ZERO,
                confidence=1.0,
                evidence=[f"exit_code=0, state={state}"],
            )

        # Rule 4 — log keyword patterns
        for root_cause, keywords in _LOG_PATTERNS:
            matched = [line[:120] for line in raw if any(kw in line for kw in keywords)]
            if matched:
                conf = min(0.75 + 0.05 * (len(matched) - 1), 0.90)
                return Classification(reason=root_cause, confidence=conf, evidence=matched[:5])

        # Rule 5 — restarting state
        if state == "restarting":
            return Classification(
                reason=RootCause.CRASH_LOOP,
                confidence=0.70,
                evidence=[f"state={state}"],
            )

        # Rule 6 — dead/removing or explicit offline context
        if state in ("dead", "removing") or (context or {}).get("node_offline"):
            return Classification(
                reason=RootCause.NODE_OFFLINE,
                confidence=0.65,
                evidence=[f"state={state}"],
            )

        # Rule 7 — unknown
        return Classification(
            reason=RootCause.UNKNOWN,
            confidence=0.30,
            evidence=[f"exit_code={exit_code}, state={state}"],
        )
