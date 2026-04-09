"""
test_iam_adapter.py — Tests for MockIAMAdapter / IAMPort (FA-14 Keycloak)
FCA SM&CR SYSC 4.7 | banxe-emi-stack
"""

from __future__ import annotations

import pytest

from services.iam.iam_port import BanxeRole, Permission, UserIdentity
from services.iam.mock_iam_adapter import MockIAMAdapter, get_iam_adapter


@pytest.fixture
def iam() -> MockIAMAdapter:
    return MockIAMAdapter()


class TestAuthentication:
    def test_valid_credentials_return_token(self, iam):
        token = iam.authenticate("mark@banxe.io", "ceo-pass")
        assert token is not None
        assert token.access_token
        assert BanxeRole.CEO in token.roles

    def test_wrong_password_returns_none(self, iam):
        token = iam.authenticate("mark@banxe.io", "wrong")
        assert token is None

    def test_unknown_user_returns_none(self, iam):
        token = iam.authenticate("nobody@banxe.io", "pass")
        assert token is None

    def test_mlro_credentials(self, iam):
        token = iam.authenticate("mlro@banxe.io", "mlro-pass")
        assert token is not None
        assert BanxeRole.MLRO in token.roles

    def test_agent_credentials(self, iam):
        token = iam.authenticate("agent-aml", "agent-pass")
        assert token is not None
        assert BanxeRole.AGENT in token.roles

    def test_token_expiry_is_set(self, iam):
        token = iam.authenticate("mark@banxe.io", "ceo-pass")
        assert token.expires_at is not None
        assert token.expires_at.tzinfo is not None


class TestTokenValidation:
    def test_valid_token_returns_identity(self, iam):
        token = iam.authenticate("mark@banxe.io", "ceo-pass")
        identity = iam.validate_token(token.access_token)
        assert identity is not None
        assert identity.username == "mark@banxe.io"

    def test_invalid_token_returns_none(self, iam):
        identity = iam.validate_token("garbage-token-xyz")
        assert identity is None

    def test_token_contains_correct_role(self, iam):
        token = iam.authenticate("mlro@banxe.io", "mlro-pass")
        identity = iam.validate_token(token.access_token)
        assert identity.has_role(BanxeRole.MLRO)

    def test_mlro_has_mfa_verified(self, iam):
        token = iam.authenticate("mlro@banxe.io", "mlro-pass")
        identity = iam.validate_token(token.access_token)
        assert identity.mfa_verified is True


class TestAuthorization:
    def _identity(self, iam, username, password) -> UserIdentity:
        token = iam.authenticate(username, password)
        return iam.validate_token(token.access_token)

    def test_mlro_can_file_sar(self, iam):
        identity = self._identity(iam, "mlro@banxe.io", "mlro-pass")
        assert iam.authorize(identity, Permission.FILE_SAR) is True

    def test_operator_cannot_file_sar(self, iam):
        identity = self._identity(iam, "operator@banxe.io", "op-pass")
        assert iam.authorize(identity, Permission.FILE_SAR) is False

    def test_cco_cannot_file_sar(self, iam):
        identity = self._identity(iam, "compliance@banxe.io", "cco-pass")
        assert iam.authorize(identity, Permission.FILE_SAR) is False

    def test_ceo_has_all_permissions(self, iam):
        identity = self._identity(iam, "mark@banxe.io", "ceo-pass")
        for perm in Permission:
            assert iam.authorize(identity, perm) is True, f"CEO missing {perm}"

    def test_mlro_can_change_watchman(self, iam):
        identity = self._identity(iam, "mlro@banxe.io", "mlro-pass")
        assert iam.authorize(identity, Permission.CHANGE_WATCHMAN_THRESHOLD) is True

    def test_operator_cannot_change_watchman(self, iam):
        identity = self._identity(iam, "operator@banxe.io", "op-pass")
        assert iam.authorize(identity, Permission.CHANGE_WATCHMAN_THRESHOLD) is False

    def test_agent_can_hold_payment(self, iam):
        identity = self._identity(iam, "agent-aml", "agent-pass")
        assert iam.authorize(identity, Permission.HOLD_PAYMENT) is True

    def test_agent_cannot_file_sar(self, iam):
        identity = self._identity(iam, "agent-aml", "agent-pass")
        assert iam.authorize(identity, Permission.FILE_SAR) is False

    def test_auditor_can_view_audit(self, iam):
        identity = self._identity(iam, "auditor@fca.gov.uk", "audit-pass")
        assert iam.authorize(identity, Permission.VIEW_AUDIT_TRAIL) is True

    def test_auditor_cannot_approve_payment(self, iam):
        identity = self._identity(iam, "auditor@fca.gov.uk", "audit-pass")
        assert iam.authorize(identity, Permission.APPROVE_PAYMENT) is False

    def test_mlro_can_approve_edd(self, iam):
        identity = self._identity(iam, "mlro@banxe.io", "mlro-pass")
        assert iam.authorize(identity, Permission.APPROVE_EDD) is True

    def test_cco_cannot_approve_edd(self, iam):
        identity = self._identity(iam, "compliance@banxe.io", "cco-pass")
        assert iam.authorize(identity, Permission.APPROVE_EDD) is False


class TestHealth:
    def test_health_true(self, iam):
        assert iam.health() is True


class TestFactory:
    def test_default_mock(self, monkeypatch):
        monkeypatch.delenv("IAM_ADAPTER", raising=False)
        adapter = get_iam_adapter()
        assert isinstance(adapter, MockIAMAdapter)

    def test_explicit_mock(self, monkeypatch):
        monkeypatch.setenv("IAM_ADAPTER", "mock")
        adapter = get_iam_adapter()
        assert isinstance(adapter, MockIAMAdapter)

    def test_keycloak_raises_without_config(self, monkeypatch):
        monkeypatch.setenv("IAM_ADAPTER", "keycloak")
        monkeypatch.delenv("KEYCLOAK_URL", raising=False)
        monkeypatch.delenv("KEYCLOAK_CLIENT_ID", raising=False)
        from services.iam.mock_iam_adapter import KeycloakAdapter

        with pytest.raises(EnvironmentError, match="KEYCLOAK_URL"):
            KeycloakAdapter()
