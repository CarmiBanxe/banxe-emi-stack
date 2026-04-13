"""
test_iam_adapter.py — Tests for MockIAMAdapter + KeycloakAdapter (FA-14 Keycloak)
FCA SM&CR SYSC 4.7 | banxe-emi-stack | S13-02

KeycloakAdapter tests use a local RSA test key pair + mock urllib to avoid
needing a live Keycloak instance. JWKS-based offline JWT validation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import time
from unittest.mock import MagicMock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from jwt.algorithms import RSAAlgorithm
import pytest

from services.iam.iam_port import AuthToken, BanxeRole, Permission, UserIdentity
from services.iam.mock_iam_adapter import KeycloakAdapter, MockIAMAdapter, get_iam_adapter

# ── Test RSA key pair (generated once per module) ─────────────────────────────

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()
_KID = "banxe-test-key-001"

_PRIVATE_PEM = _PRIVATE_KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.TraditionalOpenSSL,
    serialization.NoEncryption(),
)


def _make_jwks() -> dict:
    jwk = json.loads(RSAAlgorithm.to_jwk(_PUBLIC_KEY))
    jwk["kid"] = _KID
    jwk["use"] = "sig"
    return {"keys": [jwk]}


def _make_token(
    sub: str = "uuid-test-001",
    username: str = "operator@banxe.io",
    email: str = "operator@banxe.io",
    roles: list[str] | None = None,
    exp_delta: int = 3600,
    acr: str = "",
    audience: str = "banxe-backend",
    kid: str = _KID,
    sign_key=None,
) -> str:
    payload = {
        "sub": sub,
        "preferred_username": username,
        "email": email,
        "realm_access": {"roles": roles if roles is not None else ["OPERATOR"]},
        "acr": acr,
        "exp": int(time.time()) + exp_delta,
        "aud": audience,
        "iss": "http://localhost:8180/realms/banxe",
    }
    key = sign_key or _PRIVATE_PEM
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})


def _urlopen_mock(body: dict | bytes, status: int = 200) -> MagicMock:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    resp = MagicMock()
    resp.read.return_value = raw
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


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

        with pytest.raises(OSError, match="KEYCLOAK_URL"):
            KeycloakAdapter()


# ── KeycloakAdapter — construction ────────────────────────────────────────────


class TestKeycloakAdapterInit:
    def test_missing_url_raises_oserror(self, monkeypatch):
        monkeypatch.delenv("KEYCLOAK_URL", raising=False)
        with pytest.raises(OSError, match="KEYCLOAK_URL not set"):
            KeycloakAdapter()

    def test_jwks_url_ends_with_certs(self, monkeypatch):
        monkeypatch.setenv("KEYCLOAK_URL", "http://localhost:8180")
        adapter = KeycloakAdapter()
        assert adapter._jwks_url.endswith("/certs")

    def test_cache_initially_none(self, monkeypatch):
        monkeypatch.setenv("KEYCLOAK_URL", "http://localhost:8180")
        adapter = KeycloakAdapter()
        assert adapter._jwks_cache is None


# ── KeycloakAdapter — JWKS cache ──────────────────────────────────────────────


class TestJwksCache:
    @pytest.fixture
    def adapter(self, monkeypatch) -> KeycloakAdapter:
        monkeypatch.setenv("KEYCLOAK_URL", "http://localhost:8180")
        return KeycloakAdapter()

    def test_fetch_jwks_calls_endpoint(self, adapter):
        with patch("urllib.request.urlopen", return_value=_urlopen_mock(_make_jwks())) as m:
            result = adapter._fetch_jwks()
        assert "keys" in result
        m.assert_called_once()

    def test_second_fetch_uses_cache(self, adapter):
        with patch("urllib.request.urlopen", return_value=_urlopen_mock(_make_jwks())) as m:
            adapter._fetch_jwks()
            adapter._fetch_jwks()
        assert m.call_count == 1

    def test_cache_refreshed_after_ttl(self, adapter):
        with patch("urllib.request.urlopen", return_value=_urlopen_mock(_make_jwks())) as m:
            adapter._fetch_jwks()
            adapter._jwks_fetched_at = datetime.now(UTC) - timedelta(seconds=400)
            adapter._fetch_jwks()
        assert m.call_count == 2


# ── KeycloakAdapter — validate_token (JWKS offline) ──────────────────────────


class TestKeycloakValidateToken:
    @pytest.fixture
    def adapter(self, monkeypatch) -> KeycloakAdapter:
        monkeypatch.setenv("KEYCLOAK_URL", "http://localhost:8180")
        return KeycloakAdapter()

    def _validate(self, adapter, token) -> UserIdentity | None:
        with patch("urllib.request.urlopen", return_value=_urlopen_mock(_make_jwks())):
            return adapter.validate_token(token)

    def test_valid_token_returns_identity(self, adapter):
        assert self._validate(adapter, _make_token()) is not None

    def test_extracts_subject(self, adapter):
        identity = self._validate(adapter, _make_token(sub="uuid-ceo-999"))
        assert identity.subject == "uuid-ceo-999"

    def test_extracts_email(self, adapter):
        identity = self._validate(adapter, _make_token(email="mlro@banxe.io"))
        assert identity.email == "mlro@banxe.io"

    def test_extracts_operator_role(self, adapter):
        identity = self._validate(adapter, _make_token(roles=["OPERATOR"]))
        assert BanxeRole.OPERATOR in identity.roles

    def test_extracts_mlro_role(self, adapter):
        identity = self._validate(adapter, _make_token(roles=["MLRO"]))
        assert BanxeRole.MLRO in identity.roles

    def test_acr_mfa_sets_mfa_verified(self, adapter):
        identity = self._validate(adapter, _make_token(acr="mfa"))
        assert identity.mfa_verified is True

    def test_empty_acr_not_mfa_verified(self, adapter):
        identity = self._validate(adapter, _make_token(acr=""))
        assert identity.mfa_verified is False

    def test_unknown_roles_default_readonly(self, adapter):
        identity = self._validate(adapter, _make_token(roles=["UNKNOWN_XYZ"]))
        assert BanxeRole.READONLY in identity.roles

    def test_expired_token_returns_none(self, adapter):
        assert self._validate(adapter, _make_token(exp_delta=-10)) is None

    def test_wrong_signature_returns_none(self, adapter):
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        assert self._validate(adapter, _make_token(sign_key=other_pem)) is None

    def test_empty_jwks_returns_none(self, adapter):
        with patch("urllib.request.urlopen", return_value=_urlopen_mock({"keys": []})):
            assert adapter.validate_token(_make_token()) is None

    def test_token_expiry_from_exp_claim(self, adapter):
        identity = self._validate(adapter, _make_token(exp_delta=7200))
        assert identity is not None
        assert identity.token_expiry is not None


# ── KeycloakAdapter — authenticate ───────────────────────────────────────────


class TestKeycloakAuthenticate:
    @pytest.fixture
    def adapter(self, monkeypatch) -> KeycloakAdapter:
        monkeypatch.setenv("KEYCLOAK_URL", "http://localhost:8180")
        return KeycloakAdapter()

    def test_success_returns_auth_token(self, adapter):
        resp = _urlopen_mock({"access_token": "eyJfakeJWT", "expires_in": 3600})
        with patch("urllib.request.urlopen", return_value=resp):
            result = adapter.authenticate("operator@banxe.io", "op-pass")
        assert isinstance(result, AuthToken)
        assert result.access_token == "eyJfakeJWT"

    def test_sets_expiry(self, adapter):
        resp = _urlopen_mock({"access_token": "tok", "expires_in": 1800})
        with patch("urllib.request.urlopen", return_value=resp):
            result = adapter.authenticate("u", "p")
        diff = (result.expires_at - datetime.now(UTC)).total_seconds()
        assert 1700 < diff < 1900

    def test_failure_returns_none(self, adapter):
        with patch("urllib.request.urlopen", side_effect=Exception("401")):
            assert adapter.authenticate("bad", "creds") is None


# ── KeycloakAdapter — authorize + health ─────────────────────────────────────


class TestKeycloakAuthorizeHealth:
    @pytest.fixture
    def adapter(self, monkeypatch) -> KeycloakAdapter:
        monkeypatch.setenv("KEYCLOAK_URL", "http://localhost:8180")
        return KeycloakAdapter()

    def test_authorize_mlro_can_file_sar(self, adapter):
        identity = UserIdentity(
            subject="s",
            username="u",
            email="e@b.io",
            roles=frozenset({BanxeRole.MLRO}),
            mfa_verified=True,
        )
        assert adapter.authorize(identity, Permission.FILE_SAR) is True

    def test_authorize_operator_cannot_file_sar(self, adapter):
        identity = UserIdentity(
            subject="s",
            username="u",
            email="e@b.io",
            roles=frozenset({BanxeRole.OPERATOR}),
            mfa_verified=False,
        )
        assert adapter.authorize(identity, Permission.FILE_SAR) is False

    def test_health_true_when_reachable(self, adapter):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert adapter.health() is True

    def test_health_false_on_error(self, adapter):
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            assert adapter.health() is False
