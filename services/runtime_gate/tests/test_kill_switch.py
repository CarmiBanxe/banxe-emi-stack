from __future__ import annotations

import pytest

from services.runtime_gate.errors import AgentHalted
from services.runtime_gate.kill_switch import InMemoryKillSwitch, assert_can_act


def test_halt_makes_decision_path_refuse():
    ks = InMemoryKillSwitch()
    assert_can_act(ks, "audit_trail")  # not halted → ok
    ks.terminate("audit_trail", "operator emergency stop")
    assert ks.is_halted("audit_trail")
    with pytest.raises(AgentHalted):
        assert_can_act(ks, "audit_trail")


def test_backend_unavailable_is_fail_closed_halted():
    class BrokenKS:
        def is_halted(self, agent_id):
            raise ConnectionError("temporal unreachable")

        def terminate(self, a, r): ...
        def status(self):
            raise ConnectionError("down")

    with pytest.raises(AgentHalted):
        assert_can_act(BrokenKS(), "audit_trail")  # deny-by-default


def test_resume_clears_halt():
    ks = InMemoryKillSwitch()
    ks.terminate("x", "r")
    ks.resume("x")
    assert_can_act(ks, "x")  # no raise
