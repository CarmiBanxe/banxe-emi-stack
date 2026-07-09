"""Sprint 3 Repair Engine — decision core for automated repair actions.

GAP-A: BestSolutionScorer replaces raw scorer selection; GUARDED tier via GuardedActionExecutor.
I-27: ESCALATE is the safe fallback. Never guess, never auto-execute uncertain actions.
"""

from __future__ import annotations

import logging
import time

from services.watchdog.best_solution import BestSolutionContext, BestSolutionScorer
from services.watchdog.decision_policy import (
    ACTION_CLASS_MAP,
    ActionClass,
    ActionScorer,
    DefaultActionScorer,
    RepairAction,
)
from services.watchdog.docker_port import DockerPort
from services.watchdog.guarded_actions import GuardedActionExecutor
from services.watchdog.watchdog import LedgerPort, OllamaPort

log = logging.getLogger(__name__)


class RepairEngine:
    """Decision core: BestSolutionScorer → execute SAFE or GUARDED → escalate otherwise."""

    def __init__(
        self,
        scorer: ActionScorer | None = None,
        docker_port: DockerPort | None = None,
        ollama_port: OllamaPort | None = None,
        ledger_port: LedgerPort | None = None,
        guarded_executor: GuardedActionExecutor | None = None,
    ) -> None:
        self._raw_scorer = scorer or DefaultActionScorer()
        self._best_scorer = BestSolutionScorer(scorer=self._raw_scorer)
        self._docker = docker_port
        self._ollama = ollama_port
        self._ledger = ledger_port
        self._guarded = guarded_executor

    async def evaluate_and_act(self, failure_reason: str, context: dict) -> RepairAction:
        """Score actions via BestSolutionScorer, execute best, escalate otherwise.

        Algorithm (ADR-030 §R6):
        1. BestSolutionScorer.select() → best safe action (or ESCALATE)
        2. SAFE tier: WARM_MODEL / START_CONTAINER — direct execution
        3. GUARDED tier: GuardedActionExecutor (circuit-breaker + audit)
        4. ESCALATE / no guarded executor: log + return ESCALATE

        Args:
            failure_reason: classifier reason code
            context: may include root_cause_confidence, restart_count, node_url, etc.
        """
        rc_confidence: float = context.get("root_cause_confidence", 1.0)
        bsc = BestSolutionContext(
            failure_reason=failure_reason,
            root_cause_confidence=rc_confidence,
            restart_count=int(context.get("restart_count", 0)),
            extra={
                k: v
                for k, v in context.items()
                if k not in ("root_cause_confidence", "restart_count")
            },
        )

        selected = self._best_scorer.select(bsc)
        action_class = ACTION_CLASS_MAP.get(selected, ActionClass.MANUAL_ONLY)

        if action_class == ActionClass.SAFE:
            return await self._execute_safe(selected, context)

        if action_class == ActionClass.GUARDED:
            if not self._guarded:
                self._log_event("ESCALATE", {"reason": "no_guarded_executor", **context})
                return RepairAction.ESCALATE
            return await self._execute_guarded(selected, context)

        # MANUAL_ONLY (or unknown)
        self._log_event(
            "ESCALATE",
            {"reason": failure_reason, "selected": selected.name, **context},
        )
        return RepairAction.ESCALATE

    # ── SAFE tier (existing Sprint 3 logic) ───────────────────────────────────

    async def _execute_safe(self, action: RepairAction, context: dict) -> RepairAction:
        """Execute a SAFE-tier action and verify recovery."""
        if action == RepairAction.LOG_AND_WAIT:
            self._log_event("LOG_AND_WAIT", context)
            return RepairAction.LOG_AND_WAIT

        executed_ok = await self._execute_action(action, context)
        if executed_ok:
            verified = await self._verify_recovery(action, context)
            if verified:
                self._log_event("REPAIR_OK", {"action": action.name, **context})
                return action
            self._log_event("REPAIR_FAIL_VERIFY", {"action": action.name, **context})
        else:
            self._log_event("REPAIR_FAIL_EXECUTE", {"action": action.name, **context})

        self._log_event(
            "ESCALATE", {"reason": f"{context.get('failure_reason', '')}_repair_failed", **context}
        )
        return RepairAction.ESCALATE

    # ── GUARDED tier (GAP-A) ──────────────────────────────────────────────────

    async def _execute_guarded(self, action: RepairAction, context: dict) -> RepairAction:
        """Route to GuardedActionExecutor based on selected action."""
        assert self._guarded is not None  # checked by caller

        if action == RepairAction.RESTART_OLLAMA:
            node: str = context.get("node", context.get("node_url", "unknown"))
            return await self._guarded.restart_ollama(node)

        if action == RepairAction.CONFIG_SYNC:
            target: str = context.get("target", ".")
            return await self._guarded.config_sync(target)

        if action == RepairAction.RECREATE_CONTAINER:
            name: str = context.get("container_name", "unknown")
            return await self._guarded.recreate_container(name)

        if action == RepairAction.SYNC_OLLAMA_CTX:
            node: str = context.get("node", context.get("node_url", "unknown"))
            return await self._guarded.sync_ollama_ctx(node)

        self._log_event("ESCALATE", {"reason": "unhandled_guarded_action", "action": action.name})
        return RepairAction.ESCALATE

    # ── SAFE execution helpers (Sprint 3 unchanged) ───────────────────────────

    async def _execute_action(self, action: RepairAction, context: dict) -> bool:
        if action == RepairAction.WARM_MODEL:
            if not self._ollama:
                return False
            node_url: str = context.get("node_url", "")
            model: str = context.get("model", "")
            if not node_url or not model:
                return False
            try:
                return await self._ollama.warm(node_url, model)
            except Exception as exc:
                log.error("warm_model failed: %s", exc)
                return False

        if action == RepairAction.START_CONTAINER:
            if not self._docker:
                return False
            container_name: str = context.get("container_name", "")
            if not container_name:
                return False
            try:
                return await self._docker.start_container(container_name)
            except Exception as exc:
                log.error("start_container failed: %s", exc)
                return False

        return True

    async def _verify_recovery(self, action: RepairAction, context: dict) -> bool:
        if action == RepairAction.WARM_MODEL:
            if not self._ollama:
                return False
            node_url = context.get("node_url", "")
            model = context.get("model", "")
            if not node_url or not model:
                return False
            try:
                loaded = await self._ollama.list_models(node_url, timeout=8.0)
                return any(model in m for m in loaded)
            except Exception as exc:
                log.error("warm_model verify failed: %s", exc)
                return False

        if action == RepairAction.START_CONTAINER:
            if not self._docker:
                return False
            container_name = context.get("container_name", "")
            if not container_name:
                return False
            try:
                containers = await self._docker.list_containers()
                target = next((c for c in containers if c.name == container_name), None)
                return target is not None and target.state == "running"
            except Exception as exc:
                log.error("start_container verify failed: %s", exc)
                return False

        return True

    def _log_event(self, event: str, extra: dict | None = None) -> None:
        entry: dict = {"ts": time.time(), "event": event}
        if extra:
            entry.update(extra)
        if self._ledger:
            self._ledger.append(entry)
        log.info("[repair-engine] %s %s", event, extra or "")
