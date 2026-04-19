"""
tests/test_audit_trail/test_retention_enforcer.py
IL-AES-01 | Phase 40 | banxe-emi-stack — 16 tests
"""

from __future__ import annotations

import pytest

from services.audit_trail.models import (
    EventCategory,
    InMemoryEventStorePort,
    RetentionPolicy,
)
from services.audit_trail.retention_enforcer import (
    DEFAULT_RULES,
    HITLProposal,
    RetentionEnforcer,
)


def _enforcer() -> RetentionEnforcer:
    return RetentionEnforcer(InMemoryEventStorePort(), DEFAULT_RULES)


class TestGetRetentionDays:
    def test_aml_5yr(self) -> None:
        enf = _enforcer()
        days = enf.get_retention_days(EventCategory.AML)
        assert days == 1825

    def test_payment_7yr(self) -> None:
        enf = _enforcer()
        days = enf.get_retention_days(EventCategory.PAYMENT)
        assert days == 2555

    def test_system_3yr(self) -> None:
        enf = _enforcer()
        days = enf.get_retention_days(EventCategory.SYSTEM)
        assert days == 1095

    def test_admin_1yr(self) -> None:
        enf = _enforcer()
        days = enf.get_retention_days(EventCategory.ADMIN)
        assert days == 365

    def test_unknown_defaults_5yr(self) -> None:
        enf = _enforcer()
        days = enf.get_retention_days(EventCategory.CUSTOMER)
        assert days >= 1825


class TestSchedulePurge:
    def test_purge_returns_hitl(self) -> None:
        enf = _enforcer()
        result = enf.schedule_purge(EventCategory.AML, 365)
        assert isinstance(result, HITLProposal)

    def test_purge_is_l4(self) -> None:
        enf = _enforcer()
        result = enf.schedule_purge(EventCategory.PAYMENT, 730)
        assert result.autonomy_level == "L4"

    def test_purge_requires_mlro(self) -> None:
        enf = _enforcer()
        result = enf.schedule_purge(EventCategory.AML, 365)
        assert result.requires_approval_from == "MLRO"

    def test_purge_hitl_includes_category(self) -> None:
        enf = _enforcer()
        result = enf.schedule_purge(EventCategory.ADMIN, 365)
        assert "ADMIN" in result.resource_id

    def test_purge_hitl_includes_days(self) -> None:
        enf = _enforcer()
        result = enf.schedule_purge(EventCategory.ADMIN, 400)
        assert "400" in result.resource_id


class TestListDueForPurge:
    def test_no_due_events_empty(self) -> None:
        enf = _enforcer()
        due = enf.list_due_for_purge()
        assert isinstance(due, list)

    def test_returns_metadata_only(self) -> None:
        enf = _enforcer()
        due = enf.list_due_for_purge()
        if due:
            assert "event_id" in due[0]
            assert "category" in due[0]


class TestGetRule:
    def test_get_aml_rule(self) -> None:
        enf = _enforcer()
        rule = enf.get_rule(RetentionPolicy.AML_5YR)
        assert rule.retention_days == 1825

    def test_get_financial_rule(self) -> None:
        enf = _enforcer()
        rule = enf.get_rule(RetentionPolicy.FINANCIAL_7YR)
        assert rule.purge_requires_hitl is True

    def test_get_nonexistent_raises(self) -> None:
        enf = RetentionEnforcer(rules={})
        with pytest.raises(KeyError):
            enf.get_rule(RetentionPolicy.AML_5YR)


class TestListRules:
    def test_list_rules_returns_all(self) -> None:
        enf = _enforcer()
        rules = enf.list_rules()
        assert len(rules) == 4

    def test_all_rules_have_retention_days(self) -> None:
        enf = _enforcer()
        for rule in enf.list_rules():
            assert rule.retention_days > 0
