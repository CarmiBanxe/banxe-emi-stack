"""Pre-activation checklist (ADR-030 §9). A RED agent may go ACTIVE only when ALL
components pass: kill switch reachable · DecisionRecord emitting (REUSED —
banxe.decision_records) · budget config present · metrics wired · audit sampling on.

This returns PASS/FAIL per component; it does NOT activate anything. Activation is
a separate operator + MLRO/CEO act (ADR-030 §8) after this returns all-pass.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComponentResult:
    name: str
    ok: bool
    detail: str


def red_activation_check(
    agent_id: str,
    *,
    kill_switch,
    budget_policies,
    recorder_ready: bool,
    metrics,
    audit_sampler,
) -> list[ComponentResult]:
    """Evaluate each §9 component for ``agent_id``. ``recorder_ready`` is the REUSED
    DecisionRecord recorder's readiness (banxe.decision_records / ClickHouseDecision
    Recorder) — this module references it, never rebuilds it."""
    results: list[ComponentResult] = []

    try:
        kill_switch.status()
        results.append(ComponentResult("kill_switch", True, "reachable"))
    except Exception as exc:  # unreachable ⇒ fail (fail-closed posture)
        results.append(ComponentResult("kill_switch", False, f"unreachable: {exc!r}"))

    results.append(
        ComponentResult(
            "decision_record",
            bool(recorder_ready),
            "REUSED banxe.decision_records" if recorder_ready else "recorder not wired",
        )
    )

    has_budget = bool(budget_policies) and agent_id in budget_policies
    results.append(
        ComponentResult(
            "budget_policy",
            has_budget,
            f"policy present for {agent_id}" if has_budget else "no budget policy (fail-closed)",
        )
    )

    results.append(
        ComponentResult(
            "metrics", metrics is not None, "wired" if metrics is not None else "missing"
        )
    )

    rate = getattr(audit_sampler, "rate", 0.0) if audit_sampler is not None else 0.0
    results.append(
        ComponentResult(
            "audit_sampling", rate > 0.0, f"on (rate={rate})" if rate > 0.0 else "off/missing"
        )
    )

    return results


def all_pass(results: list[ComponentResult]) -> bool:
    return all(r.ok for r in results)


def summary(results: list[ComponentResult]) -> str:
    verdict = "PASS" if all_pass(results) else "FAIL"
    lines = [f"RED activation gate: {verdict}"]
    lines += [f"  [{'✓' if r.ok else '✗'}] {r.name}: {r.detail}" for r in results]
    return "\n".join(lines)
