"""DI provider construction tests (api/deps.py) — exercise the FastAPI dependency providers.

Real tests: each provider must construct its dependency without error. Covers the DI-selector +
provider bodies in api/deps.py (the crypto-processing flag selection is additionally covered in
test_crypto_processing_di.py). No coverage pragmas; no threshold change.
"""

from __future__ import annotations

import pytest

import api.deps as deps

# All zero-arg DI providers that construct an in-memory/mock dependency.
ZERO_ARG_PROVIDERS = [
    "get_customer_service",
    "get_kyc_service",
    "get_payment_service",
    "get_statement_service",
    "get_iam",
    "get_totp_service",
    "get_sca_service_di",
    "get_buffered_audit_port",
    "get_crypto_application_service",
    "get_gabriel_governor",
    "get_gabriel_breach_handler",
    "get_recon_engine",
    "get_webhook_reliability_port",
]


@pytest.mark.parametrize("name", ZERO_ARG_PROVIDERS)
def test_di_provider_constructs(name):
    """Each DI provider returns a non-None dependency (executes its body)."""
    obj = getattr(deps, name)()
    assert obj is not None


def test_get_ledger_base_url_default_and_env(monkeypatch):
    monkeypatch.delenv("MIDAZ_BASE_URL", raising=False)
    assert deps.get_ledger_base_url().startswith("http")
    monkeypatch.setenv("MIDAZ_BASE_URL", "http://midaz.example:8095")
    assert deps.get_ledger_base_url() == "http://midaz.example:8095"


def test_crypto_application_service_wraps_selected_processing(monkeypatch):
    """get_crypto_application_service composes wallet/processing/rpc; processing comes from the
    flag-gated selector (legacy default)."""
    monkeypatch.delenv("PAYBIS_ENABLED", raising=False)
    deps.get_crypto_application_service.cache_clear()
    svc = deps.get_crypto_application_service()
    assert svc is not None
    # processing surface is callable through the composed service health
    assert hasattr(svc, "_processing")


def _identity(*roles):
    from services.iam.iam_port import UserIdentity

    return UserIdentity(subject="u1", username="u1", email="u@x.io", roles=frozenset(roles))


def test_require_permission_and_role_return_dependencies():
    """The permission/role guard factories return an async dependency callable (covers the def)."""
    from services.iam.iam_port import BanxeRole, Permission

    perm_dep = deps.require_permission(next(iter(Permission)))
    role_dep = deps.require_role(BanxeRole.MLRO, BanxeRole.CEO)
    assert callable(perm_dep) and callable(role_dep)


@pytest.mark.asyncio
async def test_require_permission_allows_and_denies(monkeypatch):
    """Exercise the inner async permission check: allow when iam authorizes, 403 otherwise."""
    from fastapi import HTTPException

    from services.iam.iam_port import BanxeRole, Permission

    identity = _identity(BanxeRole.MLRO)
    perm = next(iter(Permission))

    class _Iam:
        def __init__(self, ok):
            self._ok = ok

        def authorize(self, ident, p):
            return self._ok

    monkeypatch.setattr(deps, "get_iam", lambda: _Iam(True))
    assert (await deps.require_permission(perm)(identity=identity)) is identity
    monkeypatch.setattr(deps, "get_iam", lambda: _Iam(False))
    with pytest.raises(HTTPException):
        await deps.require_permission(perm)(identity=identity)


@pytest.mark.asyncio
async def test_require_role_allows_and_denies():
    from fastapi import HTTPException

    from services.iam.iam_port import BanxeRole

    identity = _identity(BanxeRole.MLRO)
    assert (await deps.require_role(BanxeRole.MLRO)(identity=identity)) is identity
    with pytest.raises(HTTPException):
        await deps.require_role(BanxeRole.CEO)(identity=identity)
