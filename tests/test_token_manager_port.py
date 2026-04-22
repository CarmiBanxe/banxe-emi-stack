"""Contract test: TokenManager satisfies TokenManagerPort."""

from services.auth.token_manager import TokenManager
from services.auth.token_manager_port import TokenManagerPort


def test_token_manager_satisfies_port():
    tm: TokenManagerPort = TokenManager()
    for m in (
        "issue_access_token",
        "issue_refresh_token",
        "validate_access_token",
        "validate_refresh_token",
        "is_inactive",
        "rotate",
    ):
        assert hasattr(tm, m), f"Missing: {m}"
