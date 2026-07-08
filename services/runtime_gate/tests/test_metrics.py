from __future__ import annotations

import pytest

from services.runtime_gate.metrics import ALERT_RULES, InMemoryMetrics


def test_counters_emit():
    m = InMemoryMetrics()
    m.inc("agent_halt_triggered", "audit_trail")
    m.inc("decision_refused", "audit_trail", 3)
    assert m.value("agent_halt_triggered", "audit_trail") == 1
    assert m.value("decision_refused", "audit_trail") == 3
    assert m.value("budget_exceeded", "audit_trail") == 0


def test_unknown_counter_rejected():
    with pytest.raises(ValueError):
        InMemoryMetrics().inc("not_a_counter", "x")


def test_halt_alert_rule_documented():
    assert "agent_halt_triggered" in ALERT_RULES
    assert "PAGE" in ALERT_RULES["agent_halt_triggered"]
