"""
tests/test_token_manager.py — TokenManager unit tests
S15-FIX-2 | PSD2 RTS Art.11 | banxe-emi-stack

15 tests: inactivity timeout, refresh cycle, jti uniqueness, edge cases.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from services.auth.token_manager import TokenManager, TokenValidationError


@pytest.fixture
def tm() -> TokenManager:
    return TokenManager(
        secret_key="test-secret-32-bytes-long-for-ok",
        ttl_hours=1,
        refresh_ttl_days=7,
        inactivity_limit_sec=300,
    )


class TestTokenManagerAccessTokens:
    def test_issue_access_token_returns_tuple(self, tm):
        token, expires_at = tm.issue_access_token("cust-001")
        assert isinstance(token, str)
        assert isinstance(expires_at, datetime)

    def test_access_token_contains_sub(self, tm):
        token, _ = tm.issue_access_token("cust-42")
        payload = jwt.decode(token, "test-secret-32-bytes-long-for-ok", algorithms=["HS256"])
        assert payload["sub"] == "cust-42"

    def test_access_token_validates(self, tm):
        token, _ = tm.issue_access_token("cust-99")
        payload = tm.validate_access_token(token)
        assert payload["sub"] == "cust-99"

    def test_validate_expired_access_token_raises(self, tm):
        now = datetime.now(tz=UTC)
        payload = {
            "sub": "cust-001",
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),
        }
        expired = jwt.encode(payload, "test-secret-32-bytes-long-for-ok", algorithm="HS256")
        with pytest.raises(TokenValidationError) as exc_info:
            tm.validate_access_token(expired)
        assert exc_info.value.code == "token_expired"

    def test_validate_wrong_signature_raises(self, tm):
        token, _ = tm.issue_access_token("cust-001")
        bad_token = token[:-5] + "XXXXX"
        with pytest.raises(TokenValidationError):
            tm.validate_access_token(bad_token)

    def test_refresh_token_rejected_as_access_token(self, tm):
        refresh, _ = tm.issue_refresh_token("cust-001")
        with pytest.raises(TokenValidationError) as exc_info:
            tm.validate_access_token(refresh)
        assert exc_info.value.code == "wrong_type"


class TestTokenManagerRefreshTokens:
    def test_issue_refresh_token_has_jti(self, tm):
        token, _ = tm.issue_refresh_token("cust-001")
        payload = jwt.decode(token, "test-secret-32-bytes-long-for-ok", algorithms=["HS256"])
        assert "jti" in payload
        assert len(payload["jti"]) > 10

    def test_jti_unique_per_token(self, tm):
        t1, _ = tm.issue_refresh_token("cust-001")
        t2, _ = tm.issue_refresh_token("cust-001")
        p1 = jwt.decode(t1, "test-secret-32-bytes-long-for-ok", algorithms=["HS256"])
        p2 = jwt.decode(t2, "test-secret-32-bytes-long-for-ok", algorithms=["HS256"])
        assert p1["jti"] != p2["jti"]

    def test_refresh_token_validates(self, tm):
        token, _ = tm.issue_refresh_token("cust-007")
        payload = tm.validate_refresh_token(token)
        assert payload["sub"] == "cust-007"
        assert payload["type"] == "refresh"

    def test_access_token_rejected_as_refresh(self, tm):
        access, _ = tm.issue_access_token("cust-001")
        with pytest.raises(TokenValidationError) as exc_info:
            tm.validate_refresh_token(access)
        assert exc_info.value.code == "wrong_type"


class TestTokenManagerInactivity:
    def test_active_session_not_inactive(self, tm):
        last = datetime.now(tz=UTC) - timedelta(seconds=60)
        assert tm.is_inactive(last) is False

    def test_session_just_under_limit_not_inactive(self, tm):
        last = datetime.now(tz=UTC) - timedelta(seconds=299)
        # 299s elapsed = below limit → not inactive
        assert tm.is_inactive(last) is False

    def test_session_past_limit_is_inactive(self, tm):
        last = datetime.now(tz=UTC) - timedelta(seconds=301)
        assert tm.is_inactive(last) is True

    def test_naive_datetime_treated_as_utc(self, tm):
        # naive datetime (no tzinfo) — treated as UTC by is_inactive
        last = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=400)
        assert tm.is_inactive(last) is True


class TestTokenManagerRotation:
    def test_rotate_returns_new_tokens(self, tm):
        _, refresh = tm.issue_access_token("cust-001")
        refresh_token, _ = tm.issue_refresh_token("cust-001")
        access2, refresh2, _, _ = tm.rotate(refresh_token)
        assert isinstance(access2, str)
        assert isinstance(refresh2, str)

    def test_rotate_refresh_changes_token(self, tm):
        refresh_token, _ = tm.issue_refresh_token("cust-001")
        _, new_refresh, _, _ = tm.rotate(refresh_token)
        assert refresh_token != new_refresh
