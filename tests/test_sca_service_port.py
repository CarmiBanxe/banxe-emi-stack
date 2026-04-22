"""Contract test: SCAService satisfies ScaServicePort."""

from services.auth.sca_service import SCAService
from services.auth.sca_service_port import ScaServicePort


def test_sca_service_satisfies_port():
    svc: ScaServicePort = SCAService()
    assert hasattr(svc, "create_challenge")
    assert hasattr(svc, "verify")
    assert hasattr(svc, "resend_challenge")
    assert hasattr(svc, "get_methods")
    assert hasattr(svc, "register_otp_secret")
