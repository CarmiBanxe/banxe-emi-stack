"""Sprint 3 Decision Policy — scoring and action selection for repair engine.

I-27: only safe actions can auto-execute (reversible + high confidence).
Escalate on uncertain or high-risk scenarios.
GAP-A: ActionClass enum + GUARDED tier (RESTART_OLLAMA, CONFIG_SYNC, RECREATE_CONTAINER).
Remote config sync: SYNC_OLLAMA_CTX for OLLAMA_NUM_CTX drift on evo1/evo2.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol


class ActionClass(Enum):
    """ADR-030 action classification: determines autonomy tier."""

    SAFE = "SAFE"  # reversible, low blast radius — auto if score >= SAFE_AUTO_THRESHOLD
    GUARDED = "GUARDED"  # circuit-breaker + pre/post audit required (ADR-030 B4)
    MANUAL_ONLY = "MANUAL_ONLY"  # I-27: HITL mandatory, NEVER auto-execute


class RepairAction(Enum):
    """Repair actions ranked by risk and reversibility."""

    WARM_MODEL = auto()  # SAFE: warm a cold Ollama model
    START_CONTAINER = auto()  # SAFE: docker start an exited-cleanly container
    LOG_AND_WAIT = auto()  # SAFE: log event, wait for next cycle
    RESTART_OLLAMA = auto()  # GUARDED: systemctl restart ollama on node
    CONFIG_SYNC = auto()  # GUARDED: git pull --ff-only only, no secret generation
    RECREATE_CONTAINER = auto()  # GUARDED: stateless containers only
    SYNC_OLLAMA_CTX = auto()  # GUARDED: fix OLLAMA_NUM_CTX drift on remote node via SSH
    ESCALATE = auto()  # MANUAL_ONLY: HITL — operator must decide


ACTION_CLASS_MAP: dict[RepairAction, ActionClass] = {
    RepairAction.WARM_MODEL: ActionClass.SAFE,
    RepairAction.START_CONTAINER: ActionClass.SAFE,
    RepairAction.LOG_AND_WAIT: ActionClass.SAFE,
    RepairAction.RESTART_OLLAMA: ActionClass.GUARDED,
    RepairAction.CONFIG_SYNC: ActionClass.GUARDED,
    RepairAction.RECREATE_CONTAINER: ActionClass.GUARDED,
    RepairAction.SYNC_OLLAMA_CTX: ActionClass.GUARDED,
    RepairAction.ESCALATE: ActionClass.MANUAL_ONLY,
}


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


SAFE_AUTO_THRESHOLD: float = 0.6  # SAFE tier minimum
GUARDED_AUTO_THRESHOLD: float = 0.40  # GUARDED tier minimum (circuit-breaker adds safety)


class ActionScorer(Protocol):
    """Protocol for action scoring based on failure context."""

    def score_actions(self, failure_reason: str, context: dict) -> list[ActionScore]: ...


class DefaultActionScorer:
    """Default scoring policy covering SAFE and GUARDED tiers.

    SAFE: WARM_MODEL, START_CONTAINER, LOG_AND_WAIT.
    GUARDED (GAP-A): RESTART_OLLAMA, CONFIG_SYNC, RECREATE_CONTAINER.
    MANUAL_ONLY boundary (never in candidates): DB passwords, hyperswitch, stateful
    container recreate, schema migrations, secret generation — always ESCALATE.
    """

    def score_actions(self, failure_reason: str, context: dict) -> list[ActionScore]:
        """Score possible repair actions.

        Args:
            failure_reason: reason code from classifier
            context: extra fields (restart_count, warmup_fails, crash_loop_threshold)

        Returns:
            List of ActionScore sorted by score descending.
        """
        scores: list[ActionScore] = []

        # ── SAFE tier ────────────────────────────────────────────────────────
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

        elif failure_reason == "Exited(0)":
            restart_count = context.get("restart_count", 0)
            crash_loop_threshold = context.get("crash_loop_threshold", 10)
            if restart_count > crash_loop_threshold:
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
                        confidence=0.80,
                        time_to_recovery_s=5.0,
                    )
                )
                # confidence=0.05: logging doesn't restart the container — keeps ambiguity near 0
                scores.append(
                    ActionScore(
                        action=RepairAction.LOG_AND_WAIT,
                        reversibility=1.0,
                        blast_radius=0.0,
                        confidence=0.05,
                        time_to_recovery_s=60.0,
                    )
                )

        elif failure_reason.startswith("Exited("):
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

        # ── GUARDED tier (GAP-A) ─────────────────────────────────────────────
        elif failure_reason == "OLLAMA_PROCESS_DEAD":
            restart_count = context.get("restart_count", 0)
            crash_loop_threshold = context.get("crash_loop_threshold", 10)
            if restart_count > crash_loop_threshold:
                scores.append(
                    ActionScore(
                        action=RepairAction.ESCALATE,
                        reversibility=0.0,
                        blast_radius=1.0,
                        confidence=0.90,
                        time_to_recovery_s=3600.0,
                    )
                )
            else:
                # score = 0.95 * 0.80 * (1 - 0.15*0.5) = 0.7030
                scores.append(
                    ActionScore(
                        action=RepairAction.RESTART_OLLAMA,
                        reversibility=0.95,
                        blast_radius=0.15,
                        confidence=0.80,
                        time_to_recovery_s=45.0,
                    )
                )
                # confidence=0.05: LOG_AND_WAIT doesn't fix the process — it's a clear loser
                # Low score keeps ambiguity near 0, preserving RESTART_OLLAMA's adj>0.40
                scores.append(
                    ActionScore(
                        action=RepairAction.LOG_AND_WAIT,
                        reversibility=1.0,
                        blast_radius=0.0,
                        confidence=0.05,
                        time_to_recovery_s=300.0,
                    )
                )

        elif failure_reason == "CONFIG_DRIFT_DETECTED":
            # score = 0.85 * 0.75 * (1 - 0.10*0.5) = 0.6056
            scores.append(
                ActionScore(
                    action=RepairAction.CONFIG_SYNC,
                    reversibility=0.85,
                    blast_radius=0.10,
                    confidence=0.75,
                    time_to_recovery_s=30.0,
                )
            )
            # confidence=0.05: logging doesn't fix config drift — keeps ambiguity near 0
            scores.append(
                ActionScore(
                    action=RepairAction.LOG_AND_WAIT,
                    reversibility=1.0,
                    blast_radius=0.0,
                    confidence=0.05,
                    time_to_recovery_s=300.0,
                )
            )

        elif failure_reason == "STATELESS_CONTAINER_DEAD":
            restart_count = context.get("restart_count", 0)
            crash_loop_threshold = context.get("crash_loop_threshold", 10)
            if restart_count > crash_loop_threshold:
                scores.append(
                    ActionScore(
                        action=RepairAction.ESCALATE,
                        reversibility=0.0,
                        blast_radius=1.0,
                        confidence=0.90,
                        time_to_recovery_s=3600.0,
                    )
                )
            else:
                # score = 0.80 * 0.80 * (1 - 0.15*0.5) = 0.5920
                scores.append(
                    ActionScore(
                        action=RepairAction.RECREATE_CONTAINER,
                        reversibility=0.80,
                        blast_radius=0.15,
                        confidence=0.80,
                        time_to_recovery_s=20.0,
                    )
                )
                # confidence=0.05: logging doesn't restart the container — keeps ambiguity near 0
                scores.append(
                    ActionScore(
                        action=RepairAction.LOG_AND_WAIT,
                        reversibility=1.0,
                        blast_radius=0.0,
                        confidence=0.05,
                        time_to_recovery_s=300.0,
                    )
                )

        elif failure_reason == "OLLAMA_CTX_DRIFT":
            # score = 0.90 * 0.85 * (1 - 0.10*0.5) = 0.7268 >> GUARDED_AUTO_THRESHOLD
            scores.append(
                ActionScore(
                    action=RepairAction.SYNC_OLLAMA_CTX,
                    reversibility=0.90,
                    blast_radius=0.10,
                    confidence=0.85,
                    time_to_recovery_s=60.0,
                )
            )
            # confidence=0.05: logging doesn't fix ctx drift — keeps ambiguity near 0
            scores.append(
                ActionScore(
                    action=RepairAction.LOG_AND_WAIT,
                    reversibility=1.0,
                    blast_radius=0.0,
                    confidence=0.05,
                    time_to_recovery_s=300.0,
                )
            )

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

        scores.sort(key=lambda s: s.score, reverse=True)
        return scores
