"""Sprint 3 Decision Policy — scoring and action selection for repair engine.

I-27: only safe actions can auto-execute (reversible + high confidence).
Escalate on uncertain or high-risk scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol


class RepairAction(Enum):
    """Repair actions ranked by risk and reversibility."""

    WARM_MODEL = auto()  # warm a cold Ollama model (reversible, safe)
    START_CONTAINER = auto()  # docker start an exited-cleanly container (reversible)
    LOG_AND_WAIT = auto()  # log event, wait for next cycle (always safe)
    ESCALATE = auto()  # HITL: operator must decide (irreversible/high-risk)


@dataclass(frozen=True)
class ActionScore:
    """Scored repair action with confidence metrics."""

    action: RepairAction
    reversibility: float  # 0.0=irreversible, 1.0=fully reversible
    blast_radius: float  # 0.0=isolated, 1.0=system-wide
    confidence: float  # 0.0=no idea, 1.0=certain this fixes it
    time_to_recovery_s: float  # estimated seconds to recovery

    @property
    def score(self) -> float:
        """Higher is better. Penalise high blast_radius and low confidence.

        Formula: reversibility * confidence * (1.0 - blast_radius * 0.5)
        """
        return self.reversibility * self.confidence * (1.0 - self.blast_radius * 0.5)


SAFE_AUTO_THRESHOLD: float = 0.6  # score must exceed this for auto-execution


class ActionScorer(Protocol):
    """Protocol for action scoring based on failure context."""

    def score_actions(self, failure_reason: str, context: dict) -> list[ActionScore]: ...


class DefaultActionScorer:
    """Default implementation of action scoring policy.

    Rules:
    - WARM_MODEL for COLD/UNREACHABLE Ollama: reversibility=1.0, blast_radius=0.1,
      confidence=0.85, time_to_recovery_s=30
    - START_CONTAINER for Exited(0) containers: reversibility=0.9, blast_radius=0.2,
      confidence=0.75, time_to_recovery_s=5
    - LOG_AND_WAIT for Exited(non-zero) / crash-loop / uncertain: score below threshold
    - ESCALATE for blast_radius > 0.6 or confidence < 0.3
    """

    def score_actions(self, failure_reason: str, context: dict) -> list[ActionScore]:
        """Score possible repair actions for a failure.

        Args:
            failure_reason: reason code (e.g., "COLD_STRIKE", "Exited(0)", "crash-loop")
            context: additional context (e.g., restart_count, exit_code)

        Returns:
            List of ActionScore, sorted by score descending.
        """
        scores: list[ActionScore] = []

        # Case: model is cold or Ollama unreachable
        if failure_reason in ("COLD_STRIKE", "UNREACHABLE", "COLD"):
            scores.append(
                ActionScore(
                    action=RepairAction.WARM_MODEL,
                    reversibility=1.0,
                    blast_radius=0.1,
                    confidence=0.85,
                    time_to_recovery_s=30.0,
                )
            )
            # Also consider escalation if multiple failed warm attempts
            if context.get("warmup_fails", 0) >= 2:
                scores.append(
                    ActionScore(
                        action=RepairAction.ESCALATE,
                        reversibility=0.0,
                        blast_radius=1.0,
                        confidence=0.7,
                        time_to_recovery_s=3600.0,
                    )
                )
            else:
                scores.append(
                    ActionScore(
                        action=RepairAction.LOG_AND_WAIT,
                        reversibility=1.0,
                        blast_radius=0.0,
                        confidence=0.3,
                        time_to_recovery_s=300.0,
                    )
                )

        # Case: container exited cleanly (exit_code=0)
        elif failure_reason == "Exited(0)":
            restart_count = context.get("restart_count", 0)
            crash_loop_threshold = context.get("crash_loop_threshold", 10)
            if restart_count > crash_loop_threshold:
                # Crash-loop detected; escalate only
                scores.append(
                    ActionScore(
                        action=RepairAction.ESCALATE,
                        reversibility=0.0,
                        blast_radius=1.0,
                        confidence=0.9,
                        time_to_recovery_s=3600.0,
                    )
                )
            else:
                scores.append(
                    ActionScore(
                        action=RepairAction.START_CONTAINER,
                        reversibility=0.9,
                        blast_radius=0.2,
                        confidence=0.75,
                        time_to_recovery_s=5.0,
                    )
                )
                scores.append(
                    ActionScore(
                        action=RepairAction.LOG_AND_WAIT,
                        reversibility=1.0,
                        blast_radius=0.0,
                        confidence=0.4,
                        time_to_recovery_s=60.0,
                    )
                )

        # Case: container crashed (non-zero exit code)
        elif failure_reason.startswith("Exited("):
            # Always escalate on crash (ESCALATE first, so it's highest priority)
            scores.append(
                ActionScore(
                    action=RepairAction.ESCALATE,
                    reversibility=0.0,
                    blast_radius=0.9,
                    confidence=0.85,
                    time_to_recovery_s=3600.0,
                )
            )
            scores.append(
                ActionScore(
                    action=RepairAction.LOG_AND_WAIT,
                    reversibility=1.0,
                    blast_radius=0.0,
                    confidence=0.05,
                    time_to_recovery_s=600.0,
                )
            )

        # Case: crash-loop detected
        elif failure_reason == "crash-loop":
            scores.append(
                ActionScore(
                    action=RepairAction.ESCALATE,
                    reversibility=0.0,
                    blast_radius=0.95,
                    confidence=0.95,
                    time_to_recovery_s=3600.0,
                )
            )
            scores.append(
                ActionScore(
                    action=RepairAction.LOG_AND_WAIT,
                    reversibility=1.0,
                    blast_radius=0.0,
                    confidence=0.05,
                    time_to_recovery_s=600.0,
                )
            )

        # Default: unknown reason; be conservative
        else:
            scores.append(
                ActionScore(
                    action=RepairAction.ESCALATE,
                    reversibility=0.0,
                    blast_radius=0.8,
                    confidence=0.3,
                    time_to_recovery_s=3600.0,
                )
            )
            scores.append(
                ActionScore(
                    action=RepairAction.LOG_AND_WAIT,
                    reversibility=1.0,
                    blast_radius=0.0,
                    confidence=0.05,
                    time_to_recovery_s=600.0,
                )
            )

        # Sort by score descending (best first)
        scores.sort(key=lambda s: s.score, reverse=True)
        return scores
