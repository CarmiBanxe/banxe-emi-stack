"""Unit tests for InMemoryDeployPort — 100% coverage on deploy_port.py."""

from __future__ import annotations

import pytest

from services.deploy.deploy_port import (
    DeployEnv,
    DeploymentPlan,
    DeployPortError,
    DeployResult,
    InMemoryDeployPort,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_port(
    *,
    valid_tokens: set[str] | None = None,
    fail_on_call: bool = False,
) -> InMemoryDeployPort:
    return InMemoryDeployPort(valid_tokens=valid_tokens, fail_on_call=fail_on_call)


def _plan(env: DeployEnv = DeployEnv.STAGING) -> DeploymentPlan:
    return DeploymentPlan(
        plan_id=f"plan-{env}-001",
        target_env=env,
        artifact_ref="sha256:abc123dead",
        prepared_at="2026-06-11T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# DeployEnv
# ---------------------------------------------------------------------------


def test_deploy_env_staging_value() -> None:
    assert DeployEnv.STAGING == "staging"


def test_deploy_env_production_value() -> None:
    assert DeployEnv.PRODUCTION == "production"


# ---------------------------------------------------------------------------
# prepare_deployment happy path
# ---------------------------------------------------------------------------


async def test_prepare_staging_returns_deployment_plan() -> None:
    port = make_port()
    plan = await port.prepare_deployment(DeployEnv.STAGING)
    assert isinstance(plan, DeploymentPlan)
    assert plan.target_env is DeployEnv.STAGING
    assert plan.plan_id != ""
    assert plan.artifact_ref != ""
    assert plan.prepared_at != ""


async def test_prepare_production_returns_deployment_plan() -> None:
    port = make_port()
    plan = await port.prepare_deployment(DeployEnv.PRODUCTION)
    assert isinstance(plan, DeploymentPlan)
    assert plan.target_env is DeployEnv.PRODUCTION


# ---------------------------------------------------------------------------
# request_approval happy path
# ---------------------------------------------------------------------------


async def test_request_approval_returns_approval_request() -> None:
    port = make_port()
    plan = _plan(DeployEnv.STAGING)
    req = await port.request_approval(plan)
    assert req.plan_id == plan.plan_id
    assert req.target_env is DeployEnv.STAGING
    assert req.requested_at != ""


# ---------------------------------------------------------------------------
# execute_deployment — valid token
# ---------------------------------------------------------------------------


async def test_execute_with_valid_token_returns_deploy_result() -> None:
    port = make_port(valid_tokens={"secret-cto-token"})
    plan = _plan(DeployEnv.STAGING)
    result = await port.execute_deployment(plan, "secret-cto-token")
    assert isinstance(result, DeployResult)
    assert result.plan_id == plan.plan_id
    assert result.target_env is DeployEnv.STAGING
    assert result.status == "DEPLOYED"
    assert result.executed_at != ""


async def test_execute_production_with_valid_token() -> None:
    port = make_port(valid_tokens={"prod-token"})
    plan = _plan(DeployEnv.PRODUCTION)
    result = await port.execute_deployment(plan, "prod-token")
    assert result.target_env is DeployEnv.PRODUCTION
    assert result.status == "DEPLOYED"


# ---------------------------------------------------------------------------
# execute_deployment — refusal paths (SAFETY INVARIANT)
# ---------------------------------------------------------------------------


async def test_execute_with_none_token_raises_deploy_port_error() -> None:
    port = make_port()
    with pytest.raises(DeployPortError, match="approval required"):
        await port.execute_deployment(_plan(), None)


async def test_execute_with_invalid_token_raises_deploy_port_error() -> None:
    port = make_port(valid_tokens={"real-token"})
    with pytest.raises(DeployPortError, match="invalid token"):
        await port.execute_deployment(_plan(), "wrong-token")


async def test_execute_with_empty_string_token_raises_deploy_port_error() -> None:
    port = make_port(valid_tokens={"real-token"})
    with pytest.raises(DeployPortError):
        await port.execute_deployment(_plan(), "")


# ---------------------------------------------------------------------------
# fail_on_call flag — exercises HALT_PROVIDER_ERROR branch in agent
# ---------------------------------------------------------------------------


async def test_fail_flag_prepare_raises_deploy_port_error() -> None:
    port = make_port(fail_on_call=True)
    with pytest.raises(DeployPortError, match="configured to fail"):
        await port.prepare_deployment(DeployEnv.STAGING)


async def test_fail_flag_request_approval_raises_deploy_port_error() -> None:
    port = make_port(fail_on_call=True)
    with pytest.raises(DeployPortError, match="configured to fail"):
        await port.request_approval(_plan())


async def test_fail_flag_execute_raises_deploy_port_error() -> None:
    port = make_port(fail_on_call=True)
    with pytest.raises(DeployPortError, match="configured to fail"):
        await port.execute_deployment(_plan(), "any-token")


# ---------------------------------------------------------------------------
# default valid_tokens seed
# ---------------------------------------------------------------------------


async def test_default_valid_token_works() -> None:
    port = InMemoryDeployPort()  # uses default {"cto-valid-token"}
    result = await port.execute_deployment(_plan(), "cto-valid-token")
    assert result.status == "DEPLOYED"
