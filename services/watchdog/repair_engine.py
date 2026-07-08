"""Sprint 3 Repair Engine — decision core for automated repair actions.

I-27: ESCALATE is the safe fallback. Never guess, never auto-execute uncertain actions.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

from services.watchdog.decision_policy import (
    SAFE_AUTO_THRESHOLD,
    DefaultActionScorer,
    RepairAction,
)
from services.watchdog.docker_port import DockerPort
from services.watchdog.watchdog import LedgerPort, OllamaPort

log = logging.getLogger(__name__)


class ActionScorer(Protocol):
    """Protocol for scoring repair actions."""

    def score_actions(self, failure_reason: str, context: dict) -> list[dict]: ...


class RepairEngine:
    """Decision core: score actions, execute if safe, escalate otherwise."""

    def __init__(
        self,
        scorer: ActionScorer | None = None,
        docker_port: DockerPort | None = None,
        ollama_port: OllamaPort | None = None,
        ledger_port: LedgerPort | None = None,
    ) -> None:
        self._scorer = scorer or DefaultActionScorer()
        self._docker = docker_port
        self._ollama = ollama_port
        self._ledger = ledger_port

    async def evaluate_and_act(self, failure_reason: str, context: dict) -> RepairAction:
        """Score actions, pick best, execute if safe, escalate otherwise.

        Algorithm:
        1. Score all possible actions via ActionScorer
        2. Pick best action (highest score)
        3. If score >= SAFE_AUTO_THRESHOLD and action in {WARM_MODEL, START_CONTAINER}:
           - Execute
           - Verify via P1 health check
           - Log REPAIR_OK or REPAIR_FAIL
           - Return action taken
        4. Else: log ESCALATE, return ESCALATE

        Args:
            failure_reason: reason code (e.g., "COLD_STRIKE", "Exited(0)")
            context: additional context (e.g., warmup_fails, exit_code)

        Returns:
            RepairAction that was decided upon.
        """
        # Score all possible actions
        action_scores = self._scorer.score_actions(failure_reason, context)
        if not action_scores:
            # No actions scored; escalate
            self._log_event(
                "ESCALATE",
                {
                    "reason": failure_reason,
                    "cause": "no_actions_scored",
                    **context,
                },
            )
            return RepairAction.ESCALATE

        # Best action = highest score
        best_score = action_scores[0]
        best_action = best_score.action
        score_value = best_score.score

        # Check if auto-execute is safe
        if score_value >= SAFE_AUTO_THRESHOLD and best_action in (
            RepairAction.WARM_MODEL,
            RepairAction.START_CONTAINER,
        ):
            # Attempt execution
            executed_ok = await self._execute_action(best_action, context)
            if executed_ok:
                # Verify recovery
                verified = await self._verify_recovery(best_action, context)
                if verified:
                    self._log_event(
                        "REPAIR_OK",
                        {
                            "action": best_action.name,
                            "score": round(score_value, 3),
                            **context,
                        },
                    )
                    return best_action
                else:
                    self._log_event(
                        "REPAIR_FAIL_VERIFY",
                        {
                            "action": best_action.name,
                            "score": round(score_value, 3),
                            **context,
                        },
                    )
                    self._log_event(
                        "ESCALATE",
                        {
                            "reason": f"{failure_reason}_repair_failed_to_verify",
                            **context,
                        },
                    )
                    return RepairAction.ESCALATE
            else:
                self._log_event(
                    "REPAIR_FAIL_EXECUTE",
                    {
                        "action": best_action.name,
                        "score": round(score_value, 3),
                        **context,
                    },
                )
                self._log_event(
                    "ESCALATE",
                    {
                        "reason": f"{failure_reason}_repair_execution_failed",
                        **context,
                    },
                )
                return RepairAction.ESCALATE

        # Not safe for auto-execution; escalate
        self._log_event(
            "ESCALATE",
            {
                "reason": failure_reason,
                "best_action": best_action.name,
                "score": round(score_value, 3),
                "threshold": SAFE_AUTO_THRESHOLD,
                **context,
            },
        )
        return RepairAction.ESCALATE

    async def _execute_action(self, action: RepairAction, context: dict) -> bool:
        """Execute a repair action. Return True if execution succeeded.

        Does NOT verify recovery; that's done separately in _verify_recovery.
        """
        if action == RepairAction.WARM_MODEL:
            if not self._ollama:
                return False
            node_url: str = context.get("node_url", "")
            model: str = context.get("model", "")
            if not node_url or not model:
                return False
            try:
                result = await self._ollama.warm(node_url, model)
                return result
            except Exception as exc:
                log.error("warm_model failed: %s", exc)
                return False

        elif action == RepairAction.START_CONTAINER:
            if not self._docker:
                return False
            container_name: str = context.get("container_name", "")
            if not container_name:
                return False
            try:
                result = await self._docker.start_container(container_name)
                return result
            except Exception as exc:
                log.error("start_container failed: %s", exc)
                return False

        # LOG_AND_WAIT or ESCALATE: no execution needed
        return True

    async def _verify_recovery(self, action: RepairAction, context: dict) -> bool:
        """Verify that a repair action actually fixed the issue.

        For WARM_MODEL: re-run P1 health check and verify model is loaded.
        For START_CONTAINER: list containers and verify container is running.
        """
        if action == RepairAction.WARM_MODEL:
            if not self._ollama:
                return False
            node_url: str = context.get("node_url", "")
            model: str = context.get("model", "")
            if not node_url or not model:
                return False
            try:
                loaded = await self._ollama.list_models(node_url, timeout=8.0)
                return any(model in m for m in loaded)
            except Exception as exc:
                log.error("warm_model verify failed: %s", exc)
                return False

        elif action == RepairAction.START_CONTAINER:
            if not self._docker:
                return False
            container_name: str = context.get("container_name", "")
            if not container_name:
                return False
            try:
                containers = await self._docker.list_containers()
                target = next((c for c in containers if c.name == container_name), None)
                return target is not None and target.state == "running"
            except Exception as exc:
                log.error("start_container verify failed: %s", exc)
                return False

        # LOG_AND_WAIT or ESCALATE: no verification needed
        return True

    def _log_event(self, event: str, extra: dict | None = None) -> None:
        """Log event to ledger and logger."""
        entry: dict = {"ts": time.time(), "event": event}
        if extra:
            entry.update(extra)
        if self._ledger:
            self._ledger.append(entry)
        log.info("[repair-engine] %s %s", event, extra or "")
