from __future__ import annotations

from services.runtime_gate.audit_sampling import InMemorySampler
from services.runtime_gate.budget import load_budget
from services.runtime_gate.kill_switch import InMemoryKillSwitch
from services.runtime_gate.metrics import InMemoryMetrics
from services.runtime_gate.red_activation_check import all_pass, red_activation_check


def _wire(budget_file, **overrides: object):
    kw = dict(
        kill_switch=InMemoryKillSwitch(),
        budget_policies=load_budget(budget_file),
        recorder_ready=True,
        metrics=InMemoryMetrics(),
        audit_sampler=InMemorySampler(rate=1.0),
    )
    kw.update(overrides)
    return red_activation_check("audit_trail", **kw)


def test_all_pass_when_wired(budget_file):
    assert all_pass(_wire(budget_file)) is True


def test_fail_when_recorder_not_wired(budget_file):
    r = _wire(budget_file, recorder_ready=False)
    assert not all_pass(r)
    assert any(c.name == "decision_record" and not c.ok for c in r)


def test_fail_when_no_budget_policy(budget_file):
    # check a different agent that has no policy entry
    r = red_activation_check(
        "no_such_agent", kill_switch=InMemoryKillSwitch(),
        budget_policies=load_budget(budget_file), recorder_ready=True,
        metrics=InMemoryMetrics(), audit_sampler=InMemorySampler(1.0))
    assert not all_pass(r)
    assert any(c.name == "budget_policy" and not c.ok for c in r)


def test_fail_when_metrics_missing(budget_file):
    assert not all_pass(_wire(budget_file, metrics=None))


def test_fail_when_sampler_off(budget_file):
    assert not all_pass(_wire(budget_file, audit_sampler=InMemorySampler(rate=0.0)))


def test_fail_when_kill_switch_unreachable(budget_file):
    class BrokenKS:
        def status(self): raise ConnectionError("down")
        def is_halted(self, a): raise ConnectionError("down")
        def terminate(self, a, r): ...

    r = _wire(budget_file, kill_switch=BrokenKS())
    assert not all_pass(r)
    assert any(c.name == "kill_switch" and not c.ok for c in r)
