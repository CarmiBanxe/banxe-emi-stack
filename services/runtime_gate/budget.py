"""Budget policy (ADR-030 §9) — config-as-data, operator-owned. Over-budget ⇒ the
agent refuses (blocked, logged). No config / no policy for the agent ⇒ fail-closed.
Money is Decimal (never float)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

from .errors import BudgetConfigError, OverBudget

SCHEMA = "agent-budget-policy/v1"


@dataclass(frozen=True)
class BudgetPolicy:
    max_tokens_window: int
    max_cost_window: Decimal
    window: str


def load_budget(path: str | Path) -> dict[str, BudgetPolicy]:
    """Parse + validate. Absent/unparseable/unbounded ⇒ BudgetConfigError."""
    p = Path(path)
    if not p.exists():
        raise BudgetConfigError(f"budget config absent: {p} (fail-closed — no writes)")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise BudgetConfigError(f"unparseable budget config: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise BudgetConfigError(f"budget config schema must be {SCHEMA!r}")
    default_window = str(raw.get("window", "24h"))
    agents = raw.get("agents") or {}
    out: dict[str, BudgetPolicy] = {}
    for agent_id, spec in agents.items():
        out[agent_id] = _policy(agent_id, spec, default_window)
    return out


def _policy(agent_id: str, spec: dict, default_window: str) -> BudgetPolicy:
    try:
        tokens = int(spec["max_tokens_window"])
        cost = Decimal(str(spec["max_cost_window"]))
    except (KeyError, ValueError, InvalidOperation, TypeError) as exc:
        raise BudgetConfigError(f"invalid budget for {agent_id}: {exc}") from exc
    if tokens <= 0 or cost <= 0:
        raise BudgetConfigError(f"budget for {agent_id} must be finite positive")
    return BudgetPolicy(tokens, cost, str(spec.get("window", default_window)))


class BudgetManager:
    """In-process window accounting (sandbox). Window rollover = Outcome-C."""

    def __init__(self, policies: dict[str, BudgetPolicy], metrics=None) -> None:
        self._pol = policies
        self._used: dict[str, tuple[int, Decimal]] = {}
        self._metrics = metrics

    def charge(self, agent_id: str, tokens: int, cost: Decimal) -> None:
        """Add usage; refuse (OverBudget) if the window would be exceeded.
        Fail-closed: an agent with no policy is refused (BudgetConfigError)."""
        pol = self._pol.get(agent_id)
        if pol is None:
            raise BudgetConfigError(f"no budget policy for {agent_id} — fail-closed")
        used_t, used_c = self._used.get(agent_id, (0, Decimal(0)))
        new_t, new_c = used_t + int(tokens), used_c + Decimal(str(cost))
        if new_t > pol.max_tokens_window or new_c > pol.max_cost_window:
            if self._metrics is not None:
                self._metrics.inc("budget_exceeded", agent_id)
            raise OverBudget(
                f"{agent_id} over budget (tokens {new_t}/{pol.max_tokens_window}, "
                f"cost {new_c}/{pol.max_cost_window}) — refused"
            )
        self._used[agent_id] = (new_t, new_c)

    def used(self, agent_id: str) -> tuple[int, Decimal]:
        return self._used.get(agent_id, (0, Decimal(0)))
