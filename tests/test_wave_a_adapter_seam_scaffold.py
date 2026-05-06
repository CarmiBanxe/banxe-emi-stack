"""Scaffold tests for services/auth/legacy/ adapter seam (Wave A backend).

Verifies that the seam package imports cleanly, pydantic models build on
minimal valid data, and the scaffold classes expose the contractual surface
(without invoking unimplemented behaviour).

Constraints honoured:
- no FastAPI router wiring exercised
- no production auth flow touched
- no real BANXE.RAR code imported
"""

from __future__ import annotations

import importlib

import pytest

# ── module-import smoke ─────────────────────────────────────────────────────


def test_legacy_package_imports():
    pkg = importlib.import_module("services.auth.legacy")
    assert pkg.__doc__ is not None


def test_jwt_strategy_module_imports():
    mod = importlib.import_module("services.auth.legacy.jwt_strategy")
    assert hasattr(mod, "LegacyJwtStrategy")
    assert hasattr(mod, "ClaimsDict")


def test_jwks_models_module_imports():
    mod = importlib.import_module("services.auth.legacy.jwks_models")
    for name in ("Jwk", "Jwks", "CompleteJwt"):
        assert hasattr(mod, name), f"jwks_models missing: {name}"


def test_role_guard_module_imports_without_router_side_effects():
    """Module must not pull in any FastAPI router or app symbol at top level."""
    import inspect

    mod = importlib.import_module("services.auth.legacy.role_guard")
    assert hasattr(mod, "LegacyRoleGuard")
    assert hasattr(mod, "make_legacy_role_guard")
    # Scaffold guarantee: source must not import FastAPI router module.
    src = inspect.getsource(mod)
    assert "api.routers" not in src, "scaffold must not reference api.routers"
    assert "APIRouter" not in src, "scaffold must not register FastAPI routes"


# ── LegacyJwtStrategy contract surface ──────────────────────────────────────


def test_legacy_jwt_strategy_constructs_with_jwks_provider():
    """Production adapter requires jwks_uri or jwks_provider; provider OK for tests."""
    from services.auth.legacy.jwks_models import JwksSet
    from services.auth.legacy.jwt_strategy import LegacyJwtStrategyAdapter

    strategy = LegacyJwtStrategyAdapter(jwks_provider=lambda: JwksSet())
    assert strategy is not None


def test_legacy_jwt_strategy_requires_jwks_source():
    """Constructor must reject empty config (no jwks_uri AND no jwks_provider)."""
    from services.auth.legacy.jwt_strategy import LegacyJwtStrategyAdapter

    with pytest.raises(ValueError, match="jwks_uri or jwks_provider"):
        LegacyJwtStrategyAdapter()


# ── pydantic models on minimal valid data ───────────────────────────────────


def test_jwk_model_builds_on_minimal_valid_data():
    from services.auth.legacy.jwks_models import Jwk

    jwk = Jwk(kty="RSA", e="AQAB", n="abc-base64url", use="sig", kid="kid-1", alg="RS256")
    assert jwk.kty == "RSA"
    assert jwk.kid == "kid-1"
    assert jwk.alg == "RS256"


def test_jwks_model_builds_with_optional_pem_omitted():
    from services.auth.legacy.jwks_models import Jwks

    jwks = Jwks(kid="kid-1", alg="RS256")
    assert jwks.kid == "kid-1"
    assert jwks.pem is None


def test_jwks_model_builds_with_pem():
    from services.auth.legacy.jwks_models import Jwks

    jwks = Jwks(
        kid="kid-2", alg="RS256", pem="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
    )
    assert jwks.pem is not None
    assert jwks.pem.startswith("-----BEGIN PUBLIC KEY-----")


def test_complete_jwt_model_builds_with_typed_payload():
    from services.auth.legacy.jwks_models import CompleteJwt, Jwks, JwtPayload

    header = Jwks(kid="kid-3", alg="RS256")
    payload = JwtPayload(sub="user-001", role="MLRO", status="ACTIVE", service="tx-auth")
    complete = CompleteJwt(header=header, payload=payload)
    assert complete.header.kid == "kid-3"
    assert complete.payload.sub == "user-001"
    assert complete.payload.role == "MLRO"


# ── LegacyRoleGuard contract surface ────────────────────────────────────────


def test_legacy_role_guard_constructs_with_roles():
    from services.auth.legacy.role_guard import LegacyRoleGuard

    guard = LegacyRoleGuard(allowed_roles=["MLRO", "CEO"])
    assert guard.allowed_roles == ("MLRO", "CEO")


def test_make_legacy_role_guard_factory():
    from services.auth.legacy.role_guard import LegacyRoleGuard, make_legacy_role_guard

    guard = make_legacy_role_guard("MLRO", "OPS")
    assert isinstance(guard, LegacyRoleGuard)
    assert guard.allowed_roles == ("MLRO", "OPS")


def test_legacy_role_guard_check_invariant():
    """Production check: role ∈ allowed AND status == 'ACTIVE'."""
    from services.auth.legacy.role_guard import make_legacy_role_guard

    guard = make_legacy_role_guard("MLRO")
    assert guard.check(role="MLRO", status="ACTIVE") is True
    assert guard.check(role="MLRO", status="INACTIVE") is False
    assert guard.check(role="OPERATOR", status="ACTIVE") is False


# ── canon guard: existing auth core untouched ───────────────────────────────


def test_existing_auth_application_service_still_imports():
    """Sanity: scaffold addition must not break existing auth core imports."""
    from services.auth import auth_application_service

    assert hasattr(auth_application_service, "AuthApplicationService")


def test_existing_sca_application_service_still_imports():
    from services.auth import sca_application_service

    assert hasattr(sca_application_service, "ScaApplicationService")
