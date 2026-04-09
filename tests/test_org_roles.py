"""
tests/test_org_roles.py — OrgRoleChecker unit tests
IL-065 | banxe-emi-stack
Created: 2026-04-09

Tests the org-role HITL enforcement layer.
All 17 gates from HITL-MATRIX.yaml are covered.

Coverage areas:
  - Gate registry completeness (all 17 gates present)
  - AND logic: required_roles (ALL must be present)
  - OR logic: any_of_roles (ONE is sufficient)
  - auto_allowed: sanctions hit proceeds without approval
  - Non-delegable SAR/PEP/sanctions gates (MLRO-only)
  - CEO escalation paths
  - Role hierarchy (OPERATOR cannot unlock high-severity gates)
  - SLA values by severity
  - ApprovalResult message generation
  - gates_for_role() lookup
  - critical_gates() filter
"""

import pytest
from services.hitl.org_roles import (
    HITLGate,
    HITLTrigger,
    OrgRole,
    OrgRoleChecker,
    GATE_REGISTRY,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def checker() -> OrgRoleChecker:
    return OrgRoleChecker()


# ── 1. Registry completeness ──────────────────────────────────────────────────

class TestRegistryCompleteness:
    def test_all_17_triggers_registered(self, checker: OrgRoleChecker) -> None:
        all_triggers = set(HITLTrigger)
        assert set(GATE_REGISTRY.keys()) == all_triggers, (
            f"Missing gates: {all_triggers - set(GATE_REGISTRY.keys())}"
        )

    def test_gate_count_is_17(self, checker: OrgRoleChecker) -> None:
        assert len(checker.all_gates()) == 17

    def test_gate_ids_are_unique(self, checker: OrgRoleChecker) -> None:
        ids = [g.gate_id for g in checker.all_gates()]
        assert len(ids) == len(set(ids))

    def test_gate_ids_are_hitl_prefixed(self, checker: OrgRoleChecker) -> None:
        for gate in checker.all_gates():
            assert gate.gate_id.startswith("HITL-"), gate.gate_id

    def test_all_gates_sorted_by_gate_id(self, checker: OrgRoleChecker) -> None:
        gates = checker.all_gates()
        ids = [g.gate_id for g in gates]
        assert ids == sorted(ids)

    def test_all_gates_have_fca_basis(self, checker: OrgRoleChecker) -> None:
        for gate in checker.all_gates():
            assert gate.fca_basis, f"{gate.gate_id} missing fca_basis"

    def test_all_gates_have_valid_severity(self, checker: OrgRoleChecker) -> None:
        valid = {"critical", "high", "medium", "low"}
        for gate in checker.all_gates():
            assert gate.severity in valid, f"{gate.gate_id}: {gate.severity}"


# ── 2. HITL-001: SAR Filing (MLRO-only, non-delegable) ───────────────────────

class TestSARFiling:
    def test_mlro_can_approve_sar(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SAR_REQUIRED, {OrgRole.MLRO})
        assert result.approved is True

    def test_ceo_cannot_approve_sar_alone(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SAR_REQUIRED, {OrgRole.CEO})
        assert result.approved is False

    def test_compliance_officer_cannot_approve_sar(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SAR_REQUIRED, {OrgRole.COMPLIANCE_OFFICER})
        assert result.approved is False

    def test_operator_cannot_approve_sar(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SAR_REQUIRED, {OrgRole.OPERATOR})
        assert result.approved is False

    def test_sar_sla_is_4_hours(self, checker: OrgRoleChecker) -> None:
        gate = checker.get_gate(HITLTrigger.SAR_REQUIRED)
        assert gate.sla_hours == 4

    def test_sar_severity_is_critical(self, checker: OrgRoleChecker) -> None:
        gate = checker.get_gate(HITLTrigger.SAR_REQUIRED)
        assert gate.severity == "critical"

    def test_mlro_in_missing_roles_when_absent(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SAR_REQUIRED, {OrgRole.OPERATOR})
        assert OrgRole.MLRO in result.missing_roles

    def test_no_missing_roles_when_mlro_present(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SAR_REQUIRED, {OrgRole.MLRO})
        assert result.missing_roles == []


# ── 3. HITL-002: EDD Sign-off (MLRO or Compliance Officer) ───────────────────

class TestEDDSignOff:
    def test_mlro_satisfies_edd(self, checker: OrgRoleChecker) -> None:
        assert checker.check(HITLTrigger.EDD_REQUIRED, {OrgRole.MLRO}).approved

    def test_compliance_officer_satisfies_edd(self, checker: OrgRoleChecker) -> None:
        assert checker.check(HITLTrigger.EDD_REQUIRED, {OrgRole.COMPLIANCE_OFFICER}).approved

    def test_operator_cannot_approve_edd(self, checker: OrgRoleChecker) -> None:
        assert not checker.check(HITLTrigger.EDD_REQUIRED, {OrgRole.OPERATOR}).approved

    def test_cfo_cannot_approve_edd_alone(self, checker: OrgRoleChecker) -> None:
        assert not checker.check(HITLTrigger.EDD_REQUIRED, {OrgRole.CFO}).approved

    def test_edd_sla_is_24_hours(self, checker: OrgRoleChecker) -> None:
        assert checker.get_gate(HITLTrigger.EDD_REQUIRED).sla_hours == 24


# ── 4. HITL-003: Sanctions AUTO-BLOCK ────────────────────────────────────────

class TestSanctionsAutoBlock:
    def test_sanctions_block_is_auto_allowed(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SANCTIONS_HIT, set())
        assert result.auto_allowed is True
        assert result.approved is True

    def test_sanctions_block_needs_no_approver(self, checker: OrgRoleChecker) -> None:
        # Even with no roles, auto-block proceeds
        result = checker.check(HITLTrigger.SANCTIONS_HIT, set())
        assert result.missing_roles == []

    def test_sanctions_block_sla_is_0(self, checker: OrgRoleChecker) -> None:
        assert checker.get_gate(HITLTrigger.SANCTIONS_HIT).sla_hours == 0

    def test_sanctions_block_severity_is_critical(self, checker: OrgRoleChecker) -> None:
        assert checker.get_gate(HITLTrigger.SANCTIONS_HIT).severity == "critical"


# ── 5. HITL-004: Sanctions Reversal (MLRO + CEO, both required) ──────────────

class TestSanctionsReversal:
    def test_mlro_and_ceo_can_reverse(self, checker: OrgRoleChecker) -> None:
        result = checker.check(
            HITLTrigger.SANCTIONS_REVERSAL_REQUEST, {OrgRole.MLRO, OrgRole.CEO}
        )
        assert result.approved is True

    def test_mlro_alone_cannot_reverse_sanctions(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SANCTIONS_REVERSAL_REQUEST, {OrgRole.MLRO})
        assert result.approved is False
        assert OrgRole.CEO in result.missing_roles

    def test_ceo_alone_cannot_reverse_sanctions(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SANCTIONS_REVERSAL_REQUEST, {OrgRole.CEO})
        assert result.approved is False
        assert OrgRole.MLRO in result.missing_roles

    def test_sanctions_reversal_sla_is_2_hours(self, checker: OrgRoleChecker) -> None:
        assert checker.get_gate(HITLTrigger.SANCTIONS_REVERSAL_REQUEST).sla_hours == 2


# ── 6. HITL-005: Customer BLOCK (AML) — MLRO only ────────────────────────────

class TestCustomerBlockAML:
    def test_mlro_can_block_customer(self, checker: OrgRoleChecker) -> None:
        assert checker.check(HITLTrigger.AML_CUSTOMER_BLOCK, {OrgRole.MLRO}).approved

    def test_compliance_officer_cannot_block_customer(self, checker: OrgRoleChecker) -> None:
        assert not checker.check(
            HITLTrigger.AML_CUSTOMER_BLOCK, {OrgRole.COMPLIANCE_OFFICER}
        ).approved

    def test_coo_cannot_block_customer_for_aml(self, checker: OrgRoleChecker) -> None:
        assert not checker.check(HITLTrigger.AML_CUSTOMER_BLOCK, {OrgRole.COO}).approved


# ── 7. HITL-006: KYC Rejection ────────────────────────────────────────────────

class TestKYCRejection:
    def test_mlro_can_reject_kyc(self, checker: OrgRoleChecker) -> None:
        assert checker.check(HITLTrigger.KYC_HIGH_RISK_REJECTION, {OrgRole.MLRO}).approved

    def test_compliance_officer_can_reject_kyc(self, checker: OrgRoleChecker) -> None:
        assert checker.check(
            HITLTrigger.KYC_HIGH_RISK_REJECTION, {OrgRole.COMPLIANCE_OFFICER}
        ).approved

    def test_operator_cannot_reject_kyc_high_risk(self, checker: OrgRoleChecker) -> None:
        assert not checker.check(
            HITLTrigger.KYC_HIGH_RISK_REJECTION, {OrgRole.OPERATOR}
        ).approved


# ── 8. HITL-007: PEP Onboarding (MLRO + CEO both required) ───────────────────

class TestPEPOnboarding:
    def test_mlro_and_ceo_can_onboard_pep(self, checker: OrgRoleChecker) -> None:
        assert checker.check(
            HITLTrigger.PEP_ONBOARDING, {OrgRole.MLRO, OrgRole.CEO}
        ).approved

    def test_mlro_alone_cannot_onboard_pep(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.PEP_ONBOARDING, {OrgRole.MLRO})
        assert not result.approved
        assert OrgRole.CEO in result.missing_roles

    def test_ceo_alone_cannot_onboard_pep(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.PEP_ONBOARDING, {OrgRole.CEO})
        assert not result.approved
        assert OrgRole.MLRO in result.missing_roles

    def test_pep_sla_is_48_hours(self, checker: OrgRoleChecker) -> None:
        assert checker.get_gate(HITLTrigger.PEP_ONBOARDING).sla_hours == 48


# ── 9. HITL-008: SAR Retraction (MLRO + CEO) ─────────────────────────────────

class TestSARRetraction:
    def test_mlro_and_ceo_can_retract_sar(self, checker: OrgRoleChecker) -> None:
        assert checker.check(
            HITLTrigger.SAR_RETRACTION_REQUEST, {OrgRole.MLRO, OrgRole.CEO}
        ).approved

    def test_mlro_alone_cannot_retract_sar(self, checker: OrgRoleChecker) -> None:
        assert not checker.check(
            HITLTrigger.SAR_RETRACTION_REQUEST, {OrgRole.MLRO}
        ).approved

    def test_sar_retraction_sla_is_4_hours(self, checker: OrgRoleChecker) -> None:
        assert checker.get_gate(HITLTrigger.SAR_RETRACTION_REQUEST).sla_hours == 4


# ── 10. HITL-009: Transaction HOLD (Fraud HIGH) ───────────────────────────────

class TestTransactionHoldFraud:
    def test_mlro_can_decide_fraud_hold(self, checker: OrgRoleChecker) -> None:
        assert checker.check(HITLTrigger.FRAUD_HIGH, {OrgRole.MLRO}).approved

    def test_compliance_officer_can_decide_fraud_hold(self, checker: OrgRoleChecker) -> None:
        assert checker.check(HITLTrigger.FRAUD_HIGH, {OrgRole.COMPLIANCE_OFFICER}).approved

    def test_operator_can_decide_fraud_hold(self, checker: OrgRoleChecker) -> None:
        # Operators can approve/reject standard fraud holds
        assert checker.check(HITLTrigger.FRAUD_HIGH, {OrgRole.OPERATOR}).approved

    def test_fraud_hold_sla_is_24_hours(self, checker: OrgRoleChecker) -> None:
        assert checker.get_gate(HITLTrigger.FRAUD_HIGH).sla_hours == 24


# ── 11. HITL-010: FCA RegData Submission (CFO only) ──────────────────────────

class TestFCARegData:
    def test_cfo_can_submit_regdata(self, checker: OrgRoleChecker) -> None:
        assert checker.check(HITLTrigger.FCA_REGDATA_SUBMISSION, {OrgRole.CFO}).approved

    def test_coo_cannot_submit_regdata(self, checker: OrgRoleChecker) -> None:
        assert not checker.check(HITLTrigger.FCA_REGDATA_SUBMISSION, {OrgRole.COO}).approved

    def test_mlro_cannot_submit_regdata(self, checker: OrgRoleChecker) -> None:
        assert not checker.check(HITLTrigger.FCA_REGDATA_SUBMISSION, {OrgRole.MLRO}).approved

    def test_regdata_sla_is_168_hours(self, checker: OrgRoleChecker) -> None:
        assert checker.get_gate(HITLTrigger.FCA_REGDATA_SUBMISSION).sla_hours == 168


# ── 12. HITL-011: Safeguarding Shortfall (CFO + MLRO both) ───────────────────

class TestSafeguardingShortfall:
    def test_cfo_and_mlro_can_respond(self, checker: OrgRoleChecker) -> None:
        assert checker.check(
            HITLTrigger.SAFEGUARDING_SHORTFALL, {OrgRole.CFO, OrgRole.MLRO}
        ).approved

    def test_cfo_alone_insufficient(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SAFEGUARDING_SHORTFALL, {OrgRole.CFO})
        assert not result.approved
        assert OrgRole.MLRO in result.missing_roles

    def test_mlro_alone_insufficient(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SAFEGUARDING_SHORTFALL, {OrgRole.MLRO})
        assert not result.approved
        assert OrgRole.CFO in result.missing_roles

    def test_safeguarding_shortfall_sla_is_4_hours(self, checker: OrgRoleChecker) -> None:
        assert checker.get_gate(HITLTrigger.SAFEGUARDING_SHORTFALL).sla_hours == 4

    def test_safeguarding_shortfall_severity_is_critical(self, checker: OrgRoleChecker) -> None:
        assert checker.get_gate(HITLTrigger.SAFEGUARDING_SHORTFALL).severity == "critical"


# ── 13. HITL-012: AML Threshold Change (CRO + CEO) ───────────────────────────

class TestAMLThresholdChange:
    def test_cro_and_ceo_can_change_thresholds(self, checker: OrgRoleChecker) -> None:
        assert checker.check(
            HITLTrigger.AML_THRESHOLD_CHANGE, {OrgRole.CRO, OrgRole.CEO}
        ).approved

    def test_cro_alone_cannot_change_thresholds(self, checker: OrgRoleChecker) -> None:
        assert not checker.check(HITLTrigger.AML_THRESHOLD_CHANGE, {OrgRole.CRO}).approved

    def test_ceo_alone_cannot_change_thresholds(self, checker: OrgRoleChecker) -> None:
        assert not checker.check(HITLTrigger.AML_THRESHOLD_CHANGE, {OrgRole.CEO}).approved

    def test_mlro_cannot_change_thresholds(self, checker: OrgRoleChecker) -> None:
        assert not checker.check(HITLTrigger.AML_THRESHOLD_CHANGE, {OrgRole.MLRO}).approved

    def test_threshold_change_fca_basis_mentions_i27(self, checker: OrgRoleChecker) -> None:
        gate = checker.get_gate(HITLTrigger.AML_THRESHOLD_CHANGE)
        assert "I-27" in gate.fca_basis


# ── 14. HITL-013: Production Deploy (CTO) ────────────────────────────────────

class TestProductionDeploy:
    def test_cto_can_approve_deploy(self, checker: OrgRoleChecker) -> None:
        assert checker.check(HITLTrigger.PRODUCTION_DEPLOY, {OrgRole.CTO}).approved

    def test_coo_cannot_approve_deploy(self, checker: OrgRoleChecker) -> None:
        assert not checker.check(HITLTrigger.PRODUCTION_DEPLOY, {OrgRole.COO}).approved

    def test_deploy_severity_is_medium(self, checker: OrgRoleChecker) -> None:
        assert checker.get_gate(HITLTrigger.PRODUCTION_DEPLOY).severity == "medium"


# ── 15. HITL-014: AI Model Update (CRO + CTO) ────────────────────────────────

class TestAIModelUpdate:
    def test_cro_and_cto_can_update_model(self, checker: OrgRoleChecker) -> None:
        assert checker.check(
            HITLTrigger.AI_MODEL_UPDATE, {OrgRole.CRO, OrgRole.CTO}
        ).approved

    def test_cto_alone_cannot_update_ai_model(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.AI_MODEL_UPDATE, {OrgRole.CTO})
        assert not result.approved
        assert OrgRole.CRO in result.missing_roles

    def test_cro_alone_cannot_update_ai_model(self, checker: OrgRoleChecker) -> None:
        assert not checker.check(HITLTrigger.AI_MODEL_UPDATE, {OrgRole.CRO}).approved

    def test_ai_model_fca_basis_mentions_eu_ai_act(self, checker: OrgRoleChecker) -> None:
        gate = checker.get_gate(HITLTrigger.AI_MODEL_UPDATE)
        assert "EU AI Act" in gate.fca_basis


# ── 16. HITL-015: Security Incident CRITICAL (CTO + CEO) ─────────────────────

class TestSecurityIncidentCritical:
    def test_cto_and_ceo_can_respond(self, checker: OrgRoleChecker) -> None:
        assert checker.check(
            HITLTrigger.SECURITY_INCIDENT_CRITICAL, {OrgRole.CTO, OrgRole.CEO}
        ).approved

    def test_cto_alone_insufficient_for_critical_incident(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SECURITY_INCIDENT_CRITICAL, {OrgRole.CTO})
        assert not result.approved
        assert OrgRole.CEO in result.missing_roles

    def test_security_incident_sla_is_2_hours(self, checker: OrgRoleChecker) -> None:
        assert checker.get_gate(HITLTrigger.SECURITY_INCIDENT_CRITICAL).sla_hours == 2


# ── 17. HITL-016: Large Transaction >£50k (COO or CFO) ───────────────────────

class TestLargeTransaction:
    def test_coo_can_approve_large_tx(self, checker: OrgRoleChecker) -> None:
        assert checker.check(HITLTrigger.LARGE_TRANSACTION, {OrgRole.COO}).approved

    def test_cfo_can_approve_large_tx(self, checker: OrgRoleChecker) -> None:
        assert checker.check(HITLTrigger.LARGE_TRANSACTION, {OrgRole.CFO}).approved

    def test_operator_cannot_approve_large_tx(self, checker: OrgRoleChecker) -> None:
        assert not checker.check(HITLTrigger.LARGE_TRANSACTION, {OrgRole.OPERATOR}).approved

    def test_large_tx_sla_is_1_hour(self, checker: OrgRoleChecker) -> None:
        assert checker.get_gate(HITLTrigger.LARGE_TRANSACTION).sla_hours == 1


# ── 18. HITL-017: New Product Launch (CEO) ───────────────────────────────────

class TestNewProductLaunch:
    def test_ceo_can_approve_product_launch(self, checker: OrgRoleChecker) -> None:
        assert checker.check(HITLTrigger.NEW_PRODUCT_LAUNCH, {OrgRole.CEO}).approved

    def test_coo_cannot_launch_product(self, checker: OrgRoleChecker) -> None:
        assert not checker.check(HITLTrigger.NEW_PRODUCT_LAUNCH, {OrgRole.COO}).approved

    def test_product_launch_sla_is_720_hours(self, checker: OrgRoleChecker) -> None:
        assert checker.get_gate(HITLTrigger.NEW_PRODUCT_LAUNCH).sla_hours == 720


# ── 19. ApprovalResult message generation ────────────────────────────────────

class TestApprovalResultMessages:
    def test_approved_message_contains_gate_id(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SAR_REQUIRED, {OrgRole.MLRO})
        assert "HITL-001" in result.message

    def test_blocked_message_contains_missing_role(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SAR_REQUIRED, {OrgRole.OPERATOR})
        assert "MLRO" in result.message
        assert "BLOCKED" in result.message

    def test_auto_allowed_message(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SANCTIONS_HIT, set())
        assert "auto-allowed" in result.message

    def test_blocked_message_contains_fca_basis(self, checker: OrgRoleChecker) -> None:
        result = checker.check(HITLTrigger.SAR_REQUIRED, {OrgRole.OPERATOR})
        assert "POCA" in result.message


# ── 20. Utility methods ───────────────────────────────────────────────────────

class TestUtilityMethods:
    def test_gates_for_mlro_includes_sar_and_edd(self, checker: OrgRoleChecker) -> None:
        gates = checker.gates_for_role(OrgRole.MLRO)
        gate_ids = [g.gate_id for g in gates]
        assert "HITL-001" in gate_ids   # SAR
        assert "HITL-002" in gate_ids   # EDD

    def test_gates_for_operator_is_only_fraud_hold(self, checker: OrgRoleChecker) -> None:
        gates = checker.gates_for_role(OrgRole.OPERATOR)
        assert len(gates) == 1
        assert gates[0].gate_id == "HITL-009"

    def test_critical_gates_count(self, checker: OrgRoleChecker) -> None:
        critical = checker.critical_gates()
        # HITL-001,003,004,005,007,008,011,015 = 8 critical gates
        assert len(critical) == 8

    def test_critical_gates_are_all_critical_severity(self, checker: OrgRoleChecker) -> None:
        for gate in checker.critical_gates():
            assert gate.severity == "critical"

    def test_get_gate_returns_correct_gate(self, checker: OrgRoleChecker) -> None:
        gate = checker.get_gate(HITLTrigger.SAR_REQUIRED)
        assert isinstance(gate, HITLGate)
        assert gate.gate_id == "HITL-001"
        assert gate.trigger == HITLTrigger.SAR_REQUIRED

    def test_ceo_has_most_gates(self, checker: OrgRoleChecker) -> None:
        # CEO is required for many critical decisions
        ceo_gates = checker.gates_for_role(OrgRole.CEO)
        operator_gates = checker.gates_for_role(OrgRole.OPERATOR)
        assert len(ceo_gates) > len(operator_gates)

    def test_mlro_has_more_gates_than_coo(self, checker: OrgRoleChecker) -> None:
        mlro_gates = checker.gates_for_role(OrgRole.MLRO)
        coo_gates = checker.gates_for_role(OrgRole.COO)
        assert len(mlro_gates) > len(coo_gates)

    def test_approvers_needed_returns_required_roles(self, checker: OrgRoleChecker) -> None:
        gate = checker.get_gate(HITLTrigger.PEP_ONBOARDING)
        needed = gate.approvers_needed()
        assert OrgRole.MLRO in needed
        assert OrgRole.CEO in needed

    def test_auto_block_has_no_approvers_needed(self, checker: OrgRoleChecker) -> None:
        gate = checker.get_gate(HITLTrigger.SANCTIONS_HIT)
        assert gate.approvers_needed() == set()


# ── 21. Edge cases — empty/superfluous roles ──────────────────────────────────

class TestEdgeCases:
    def test_extra_roles_dont_block_approval(self, checker: OrgRoleChecker) -> None:
        # Adding unrelated roles to a valid set should not break approval
        result = checker.check(
            HITLTrigger.SAR_REQUIRED,
            {OrgRole.MLRO, OrgRole.OPERATOR, OrgRole.CEO},
        )
        assert result.approved is True

    def test_empty_roles_fails_any_non_auto_gate(self, checker: OrgRoleChecker) -> None:
        for trigger in HITLTrigger:
            gate = GATE_REGISTRY[trigger]
            if not gate.auto_allowed:
                result = checker.check(trigger, set())
                assert not result.approved, f"{gate.gate_id} should fail with empty roles"

    def test_auto_allowed_gate_returns_approved_regardless_of_roles(
        self, checker: OrgRoleChecker
    ) -> None:
        # Sanctions auto-block: any role set (or none) returns approved
        for roles in [set(), {OrgRole.OPERATOR}, {OrgRole.MLRO, OrgRole.CEO}]:
            result = checker.check(HITLTrigger.SANCTIONS_HIT, roles)
            assert result.approved is True

    def test_approval_result_is_not_auto_allowed_for_manual_gates(
        self, checker: OrgRoleChecker
    ) -> None:
        result = checker.check(HITLTrigger.SAR_REQUIRED, {OrgRole.MLRO})
        assert result.auto_allowed is False
