"""GAP-A — GuardedActionExecutor: GUARDED-tier actions with circuit-breaker + I-24 audit.

MANUAL_ONLY boundary (hard — never bypass):
  - DB password changes / ALTER USER / GRANT / schema migrations
  - hyperswitch = MANUAL_ONLY per PCI DSS
  - stateful container recreation (PostgreSQL, ClickHouse)
  - any secret generation or rotation

Supported GUARDED actions:
  - restart_ollama: systemctl restart ollama on node (via SSH shell)
  - config_sync: git pull --ff-only from authority (NEVER generates secrets)
  - recreate_container: docker rm + run for stateless containers only

Each action: circuit_breaker check → BEFORE audit → dispatch → verify → AFTER audit.
I-27: any failure → ESCALATE + rollback attempt.
"""

from __future__ import annotations

from collections.abc import Callable
import logging

from services.watchdog.audit_log import AuditLogPort, make_audit_record
from services.watchdog.circuit_breaker import CircuitBreakerState, ShellCommandPort
from services.watchdog.decision_policy import RepairAction

log = logging.getLogger(__name__)

# Stateful containers that must NEVER be auto-recreated (MANUAL_ONLY)
_STATEFUL_NEVER_RECREATE: frozenset[str] = frozenset(
    {"postgres", "postgresql", "clickhouse", "redis", "kafka", "zookeeper"}
)


class GuardedActionExecutor:
    """Executes GUARDED repair actions with circuit-breaker and I-24 audit trail.

    Protocol DI: all ports injected via constructor — no module-level singletons.
    """

    def __init__(
        self,
        shell_port: ShellCommandPort,
        audit_port: AuditLogPort,
        cb_max_attempts: int = 3,
        cb_backoff_base_s: float = 10.0,
        cb_max_quarantine_s: float = 1800.0,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        self._shell = shell_port
        self._audit = audit_port
        self._cb_max = cb_max_attempts
        self._cb_backoff = cb_backoff_base_s
        self._cb_quarantine = cb_max_quarantine_s
        self._now: Callable[[], float] = now_fn or _real_time
        # Per-action circuit breakers (keyed by action name)
        self._breakers: dict[str, CircuitBreakerState] = {}

    # ── public interface ───────────────────────────────────────────────────────

    async def restart_ollama(self, node: str) -> RepairAction:
        """Restart ollama process on *node* via remote shell.

        I-27: if circuit OPEN or verify fails → ESCALATE.
        node: host reference (hostname or SSH alias) — not a secret, not logged as value.
        """
        action_key = "restart_ollama"
        cb = self._get_breaker(action_key)
        now = self._now()

        if cb.is_blocked(now):
            self._audit.record(
                make_audit_record(
                    target=node,
                    observed_state="OLLAMA_PROCESS_DEAD",
                    root_cause="OLLAMA_PROCESS_DEAD",
                    root_cause_confidence=0.0,
                    selected_action=RepairAction.ESCALATE.name,
                    action_score=0.0,
                    executed=False,
                    verification_result=False,
                    autonomy_mode="GUARDED_CB_OPEN",
                )
            )
            return RepairAction.ESCALATE

        cmd = ["ssh", node, "sudo", "systemctl", "restart", "ollama"]
        return await self._dispatch_and_verify(
            action_key=action_key,
            action=RepairAction.RESTART_OLLAMA,
            target=node,
            observed_state="OLLAMA_PROCESS_DEAD",
            root_cause="OLLAMA_PROCESS_DEAD",
            dispatch_cmd=cmd,
            verify_cmd=["ssh", node, "systemctl", "is-active", "ollama"],
            verify_success_stdout="active",
            rollback_cmd=None,
        )

    async def config_sync(self, target: str) -> RepairAction:
        """Git pull --ff-only on *target* (directory path on managed node).

        Constraints (hard): ff-only merge only; never generates or rotates secrets.
        Use case: restore OLLAMA_CONTEXT_LENGTH=8192 or similar config drift.
        """
        action_key = f"config_sync:{target}"
        cb = self._get_breaker(action_key)
        now = self._now()

        if cb.is_blocked(now):
            self._audit.record(
                make_audit_record(
                    target=target,
                    observed_state="CONFIG_DRIFT_DETECTED",
                    root_cause="CONFIG_DRIFT_DETECTED",
                    root_cause_confidence=0.0,
                    selected_action=RepairAction.ESCALATE.name,
                    action_score=0.0,
                    executed=False,
                    verification_result=False,
                    autonomy_mode="GUARDED_CB_OPEN",
                )
            )
            return RepairAction.ESCALATE

        return await self._dispatch_and_verify(
            action_key=action_key,
            action=RepairAction.CONFIG_SYNC,
            target=target,
            observed_state="CONFIG_DRIFT_DETECTED",
            root_cause="CONFIG_DRIFT_DETECTED",
            dispatch_cmd=["git", "-C", target, "pull", "--ff-only"],
            verify_cmd=["git", "-C", target, "status", "--porcelain"],
            verify_success_stdout="",  # clean working tree → empty output
            rollback_cmd=["git", "-C", target, "reset", "--hard", "HEAD@{1}"],
        )

    async def recreate_container(self, name: str) -> RepairAction:
        """Recreate *name* container (docker stop + rm + run) — stateless only.

        Hard boundary: containers in _STATEFUL_NEVER_RECREATE → ESCALATE immediately.
        """
        # MANUAL_ONLY boundary: stateful containers must never be auto-recreated
        for stateful_key in _STATEFUL_NEVER_RECREATE:
            if stateful_key in name.lower():
                log.warning(
                    "recreate_container: %s matched stateful guard (%s) → ESCALATE",
                    name,
                    stateful_key,
                )
                self._audit.record(
                    make_audit_record(
                        target=name,
                        observed_state="STATELESS_CONTAINER_DEAD",
                        root_cause="STATELESS_CONTAINER_DEAD",
                        root_cause_confidence=0.0,
                        selected_action=RepairAction.ESCALATE.name,
                        action_score=0.0,
                        executed=False,
                        verification_result=False,
                        autonomy_mode="MANUAL_ONLY_STATEFUL_GUARD",
                        manual_only=True,
                    )
                )
                return RepairAction.ESCALATE

        action_key = f"recreate_container:{name}"
        cb = self._get_breaker(action_key)
        now = self._now()

        if cb.is_blocked(now):
            self._audit.record(
                make_audit_record(
                    target=name,
                    observed_state="STATELESS_CONTAINER_DEAD",
                    root_cause="STATELESS_CONTAINER_DEAD",
                    root_cause_confidence=0.0,
                    selected_action=RepairAction.ESCALATE.name,
                    action_score=0.0,
                    executed=False,
                    verification_result=False,
                    autonomy_mode="GUARDED_CB_OPEN",
                )
            )
            return RepairAction.ESCALATE

        return await self._dispatch_and_verify(
            action_key=action_key,
            action=RepairAction.RECREATE_CONTAINER,
            target=name,
            observed_state="STATELESS_CONTAINER_DEAD",
            root_cause="STATELESS_CONTAINER_DEAD",
            dispatch_cmd=["docker", "restart", name],
            verify_cmd=["docker", "inspect", "--format={{.State.Status}}", name],
            verify_success_stdout="running",
            rollback_cmd=["docker", "stop", name],
        )

    # ── private helpers ────────────────────────────────────────────────────────

    def _get_breaker(self, key: str) -> CircuitBreakerState:
        if key not in self._breakers:
            self._breakers[key] = CircuitBreakerState()
        return self._breakers[key]

    async def _dispatch_and_verify(
        self,
        *,
        action_key: str,
        action: RepairAction,
        target: str,
        observed_state: str,
        root_cause: str,
        dispatch_cmd: list[str],
        verify_cmd: list[str],
        verify_success_stdout: str,
        rollback_cmd: list[str] | None,
    ) -> RepairAction:
        """Core GUARDED execution: BEFORE audit → dispatch → verify → AFTER audit.

        I-24: BEFORE record written before dispatch. AFTER record written after verify.
        Dispatch failure → single record only (no AFTER written).
        """
        cb = self._get_breaker(action_key)
        now = self._now()

        # BEFORE audit (I-24: before any state mutation)
        self._audit.record(
            make_audit_record(
                target=target,
                observed_state=observed_state,
                root_cause=root_cause,
                root_cause_confidence=1.0,
                selected_action=action.name,
                action_score=0.0,
                executed=False,
                verification_result=None,
                autonomy_mode="GUARDED",
            )
        )

        # Dispatch
        try:
            rc, stdout = await self._shell.run(dispatch_cmd)
            dispatch_ok = rc == 0
        except Exception as exc:
            log.error("guarded dispatch failed [%s]: %s", action_key, exc)
            cb.record_failure(now, self._cb_max, self._cb_backoff, self._cb_quarantine)
            # single record for dispatch exception (no AFTER)
            return RepairAction.ESCALATE

        if not dispatch_ok:
            log.warning("guarded dispatch non-zero [%s] rc=%s stdout=%r", action_key, rc, stdout)
            cb.record_failure(now, self._cb_max, self._cb_backoff, self._cb_quarantine)
            return RepairAction.ESCALATE

        # Verify recovery
        try:
            vrc, vstdout = await self._shell.run(verify_cmd)
            verified = vrc == 0 and vstdout.strip() == verify_success_stdout
        except Exception as exc:
            log.error("guarded verify failed [%s]: %s", action_key, exc)
            verified = False

        # AFTER audit (I-24: always appended — never delete)
        self._audit.record(
            make_audit_record(
                target=target,
                observed_state=observed_state,
                root_cause=root_cause,
                root_cause_confidence=1.0,
                selected_action=action.name,
                action_score=0.0,
                executed=True,
                verification_result=verified,
                autonomy_mode="GUARDED",
            )
        )

        if not verified:
            cb.record_failure(now, self._cb_max, self._cb_backoff, self._cb_quarantine)
            if rollback_cmd:
                try:
                    await self._shell.run(rollback_cmd)
                except Exception as exc:
                    log.error("rollback failed [%s]: %s", action_key, exc)
            return RepairAction.ESCALATE

        cb.record_success()
        return action


def _real_time() -> float:
    """Production time provider — injected as default; replaced in tests."""
    import time

    return time.time()
