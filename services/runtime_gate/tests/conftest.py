from __future__ import annotations

import pytest

BUDGET_YAML = """\
schema: agent-budget-policy/v1
window: 24h
agents:
  audit_trail:
    max_tokens_window: 1000
    max_cost_window: "2.00"
    window: 24h
"""


@pytest.fixture
def budget_file(tmp_path):
    p = tmp_path / "agent-budget-policy.yaml"
    p.write_text(BUDGET_YAML, encoding="utf-8")
    return p
