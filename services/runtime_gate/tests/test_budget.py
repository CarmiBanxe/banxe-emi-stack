from __future__ import annotations

from decimal import Decimal

import pytest

from services.runtime_gate.budget import BudgetManager, load_budget
from services.runtime_gate.errors import BudgetConfigError, OverBudget
from services.runtime_gate.metrics import InMemoryMetrics


def test_config_loads_as_decimal(budget_file):
    pol = load_budget(budget_file)
    assert pol["audit_trail"].max_tokens_window == 1000
    assert pol["audit_trail"].max_cost_window == Decimal("2.00")
    assert isinstance(pol["audit_trail"].max_cost_window, Decimal)


def test_over_budget_refuses_and_counts(budget_file):
    m = InMemoryMetrics()
    bm = BudgetManager(load_budget(budget_file), metrics=m)
    bm.charge("audit_trail", 600, Decimal("1.00"))  # within
    with pytest.raises(OverBudget):
        bm.charge("audit_trail", 600, Decimal("0.10"))  # 1200 > 1000 tokens
    assert m.value("budget_exceeded", "audit_trail") == 1


def test_no_config_is_fail_closed(tmp_path):
    with pytest.raises(BudgetConfigError):
        load_budget(tmp_path / "absent.yaml")


def test_no_policy_for_agent_is_fail_closed(budget_file):
    bm = BudgetManager(load_budget(budget_file))
    with pytest.raises(BudgetConfigError):
        bm.charge("unknown_agent", 1, Decimal("0.01"))


def test_bad_schema_is_fail_closed(tmp_path):
    p = tmp_path / "b.yaml"
    p.write_text("schema: bogus/v9\nagents: {}\n", encoding="utf-8")
    with pytest.raises(BudgetConfigError):
        load_budget(p)
