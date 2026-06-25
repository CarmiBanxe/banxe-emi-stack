"""
test_org_roles_dept_heads.py — Sprint-3 / GAP-078 dept-head agent → role → gate wiring
banxe-emi-stack | services/hitl/org_roles.py

Verifies the 10 activated department-head agents resolve to the correct approver
OrgRole and to the correct existing HITL gates (HITL-MATRIX.yaml unchanged).
"""

from __future__ import annotations

import pytest

from services.hitl.org_roles import (
    DEPT_HEAD_AGENTS,
    HITLTrigger,
    OrgRole,
    OrgRoleChecker,
    gates_for_agent,
    role_for_agent,
)

# Expected agent → role binding (STAFF-MATRIX-v2 §2).
_EXPECTED = {
    "ceo_orchestration_agent": OrgRole.CEO,
    "board_reporting_agent": None,
    "internal_audit_agent": OrgRole.INTERNAL_AUDITOR,
    "risk_oversight_agent": OrgRole.CRO,
    "compliance_monitoring_agent": OrgRole.COMPLIANCE_OFFICER,
    "cfo_orchestration_agent": OrgRole.CFO,
    "coo_operations_agent": OrgRole.COO,
    "cto_platform_agent": OrgRole.CTO,
    "front_office_agent": None,
    "legal_corporate_agent": None,
}

_APPROVERS = [a for a, r in _EXPECTED.items() if r is not None]
_NON_APPROVERS = [a for a, r in _EXPECTED.items() if r is None]


class TestRegistry:
    def test_all_ten_agents_registered(self) -> None:
        assert set(DEPT_HEAD_AGENTS) == set(_EXPECTED)
        assert len(DEPT_HEAD_AGENTS) == 10

    @pytest.mark.parametrize("agent,role", list(_EXPECTED.items()))
    def test_role_binding(self, agent: str, role: OrgRole | None) -> None:
        assert role_for_agent(agent) == role

    def test_unknown_agent_raises(self) -> None:
        with pytest.raises(KeyError):
            role_for_agent("nonexistent_agent")


class TestGatesForApprovers:
    @pytest.mark.parametrize("agent", _APPROVERS)
    def test_approver_resolves_to_its_role_gates(self, agent: str) -> None:
        role = role_for_agent(agent)
        gates = gates_for_agent(agent)
        # Every gate returned must list this agent's role as required or sufficient.
        for g in gates:
            assert role in g.required_roles or role in g.any_of_roles
        # Resolution matches the role-level resolver (single source of truth).
        assert gates == OrgRoleChecker().gates_for_role(role)

    def test_ceo_can_act_on_new_product_launch(self) -> None:
        ids = {g.trigger for g in gates_for_agent("ceo_orchestration_agent")}
        assert HITLTrigger.NEW_PRODUCT_LAUNCH in ids  # HITL-017 (CEO required)

    def test_cfo_can_act_on_fca_regdata(self) -> None:
        ids = {g.trigger for g in gates_for_agent("cfo_orchestration_agent")}
        assert HITLTrigger.FCA_REGDATA_SUBMISSION in ids  # HITL-010 (CFO required)

    def test_cto_can_act_on_production_deploy(self) -> None:
        ids = {g.trigger for g in gates_for_agent("cto_platform_agent")}
        assert HITLTrigger.PRODUCTION_DEPLOY in ids  # HITL-013 (CTO required)


class TestNonApprovers:
    @pytest.mark.parametrize("agent", _NON_APPROVERS)
    def test_non_approver_has_no_gates(self, agent: str) -> None:
        assert gates_for_agent(agent) == []


class TestMlroNotDuplicated:
    def test_no_dept_head_binds_to_mlro(self) -> None:
        # MLRO / Financial Crime is the independent banxe_aml_orchestrator line —
        # NOT one of the 10 dept-heads (canon de-duplication).
        assert OrgRole.MLRO not in DEPT_HEAD_AGENTS.values()
