"""End-to-end integration: production DI wiring of TOTPService into SCAService.

Sprint 4 Track A Block 7 — verifies the FastAPI Depends chain:
    router → get_sca_application_service(Depends(get_two_factor_port))
          → ScaApplicationService(sca_service=get_sca_service(two_factor=TOTPService()))

Closes NEXT_SESSION_START.md Task 4 production wiring (Block 6 covered the
test surface; Block 7 wires the real TOTPService at the router-DI layer).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from api.deps import get_totp_service, get_two_factor_port
from api.routers.auth import get_sca_application_service
from services.auth.sca_application_service import ScaApplicationService
from services.auth.sca_service import SCAService, get_sca_service
from services.auth.two_factor import TOTPService


@pytest.fixture
def reset_sca_singleton() -> Iterator[None]:
    """Reset the module-level SCAService singleton before/after the test.

    Block 7 verifies production wiring through the lazy-once factory; tests
    must run with a fresh singleton to observe the TOTPService injection.
    """
    import services.auth.sca_service as sca_mod

    original = sca_mod._sca_service
    sca_mod._sca_service = None
    yield
    sca_mod._sca_service = original


def test_get_sca_service_with_totp_kwarg_wires_two_factor(
    reset_sca_singleton: None,
) -> None:
    """get_sca_service(two_factor=TOTPService()) wires the singleton with port.

    Production path verification: when the router factory passes a TOTPService
    instance, the lazy-instantiated singleton SCAService receives it as the
    TwoFactorPort dependency and routes _verify_otp through the port.
    """
    totp = TOTPService()
    svc = get_sca_service(two_factor=totp)

    assert isinstance(svc, SCAService)
    assert svc._two_factor is totp


def test_get_sca_application_service_chains_real_totp(
    reset_sca_singleton: None,
) -> None:
    """Router factory builds ScaApplicationService with TOTPService in chain.

    Verifies the production FastAPI Depends pattern end-to-end:
        get_sca_application_service(two_factor=TOTPService_singleton)
            → ScaApplicationService(sca_service=SCAService(two_factor=TOTPService))

    The resulting SCAService instance has the TOTPService accessible via
    `_two_factor`, so OTP verification at runtime delegates to it.
    """
    totp_singleton = get_totp_service()
    assert isinstance(totp_singleton, TOTPService)

    # Direct call simulating FastAPI's Depends resolution.
    sca_app = get_sca_application_service(two_factor=totp_singleton)

    assert isinstance(sca_app, ScaApplicationService)
    assert sca_app.sca_service._two_factor is totp_singleton


def test_get_two_factor_port_is_get_totp_service_alias() -> None:
    """get_two_factor_port is a semantic alias for get_totp_service.

    Both providers must return the same singleton instance, since the
    @lru_cache(maxsize=1) ensures TOTPService is constructed once per
    process and reused across both names.
    """
    assert get_two_factor_port is get_totp_service
    assert get_two_factor_port() is get_totp_service()
