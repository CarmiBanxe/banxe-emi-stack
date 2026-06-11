"""services/deploy/deploy_port.py — DeployPort: governed deployment CONTRACT
(ADR-081, CTO DeployAgent — SAFETY-CRITICAL).

EXPLICIT BOUNDARY:
  prepare_deployment  — read/validate only; NO side effect; NO deployment.
  request_approval    — propose only; raises the action to the human gate.
  execute_deployment  — executes the deployment ONLY when a valid approval_token
                        is supplied. No token → immediate refusal (DeployPortError).

SAFETY INVARIANT: execute_deployment MUST raise DeployPortError if approval_token
is None or is not a recognised valid CTO approval token. For PRODUCTION this is
mandatory; STAGING also requires a valid CTO review token. There is NO
autonomous-execute path on this port: every execute call requires a token that the
port validates as the final defense-in-depth layer.

No real CI/CD integration (I-10) — InMemoryDeployPort only in this sprint.
"""

from __future__ import annotations

import abc
from abc import abstractmethod
from dataclasses import dataclass
from enum import StrEnum

# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class DeployPortError(Exception):
    """Base error for DeployPort operation failures.

    Adapters raise this (or a subclass) when a deployment operation fails or
    when the approval_token is None / invalid. DeployAgent catches it, emits
    one lineage record (executed=False), then re-raises — defense-in-depth
    (ADR-046 / ADR-081). Correlate failures via AgentDecisionRecord.correlation_id.
    """


# ---------------------------------------------------------------------------
# Value types (frozen=True — immutable after construction)
# ---------------------------------------------------------------------------


class DeployEnv(StrEnum):
    """Deployment target environments."""

    STAGING = "staging"
    PRODUCTION = "production"


@dataclass(frozen=True)
class DeploymentPlan:
    """A proposed deployment plan (read/validate only — no side effect).

    Returned by prepare_deployment; passed as input to execute_deployment.
    triggering_event in lineage records uses plan_id + target_env only —
    artifact_ref is never surfaced in a lineage record (R-SEC).
    """

    plan_id: str
    target_env: DeployEnv
    artifact_ref: str
    prepared_at: str


@dataclass(frozen=True)
class ApprovalRequest:
    """A raised approval request (propose-only — no side effect).

    Returned by request_approval; presented to the authorised approver.
    """

    plan_id: str
    target_env: DeployEnv
    requested_at: str


@dataclass(frozen=True)
class DeployResult:
    """The result of a successfully executed deployment."""

    plan_id: str
    target_env: DeployEnv
    status: str
    executed_at: str


# ---------------------------------------------------------------------------
# Abstract port (CONTRACT, ADR-081)
# ---------------------------------------------------------------------------


class DeployPort(abc.ABC):
    """Abstract CONTRACT for the governed deployment port (ADR-081 CTO deploy agent).

    SAFETY INVARIANT: execute_deployment MUST raise DeployPortError when
    approval_token is None or not a recognised valid CTO approval token.
    This check is the final defense-in-depth layer; the agent also enforces it,
    but the port is the authority on token validity.

    Conformance rules:
      prepare_deployment  — read/validate only; MUST NOT trigger any deployment.
      request_approval    — propose only; MUST NOT execute any deployment.
      execute_deployment  — requires a non-None, recognised approval_token; raises
                            DeployPortError otherwise (no bypass path exists).
    """

    @abstractmethod
    async def prepare_deployment(self, target_env: DeployEnv) -> DeploymentPlan:
        """Read/validate the deployment plan for the given environment.

        Read-only; MUST NOT trigger any deployment or state change.

        Returns:
            DeploymentPlan with plan_id, target_env, artifact_ref, prepared_at.

        Raises:
            DeployPortError: if the plan cannot be prepared.
        """
        ...  # pragma: no cover

    @abstractmethod
    async def request_approval(self, plan: DeploymentPlan) -> ApprovalRequest:
        """Raise an approval request to the human gate (propose-only).

        Does NOT execute the deployment. Returns an ApprovalRequest that the
        caller presents to the authorised CTO approver.

        Returns:
            ApprovalRequest with plan_id, target_env, requested_at.

        Raises:
            DeployPortError: if the approval request cannot be raised.
        """
        ...  # pragma: no cover

    @abstractmethod
    async def execute_deployment(
        self,
        plan: DeploymentPlan,
        approval_token: str | None,
    ) -> DeployResult:
        """Execute the deployment using the provided CTO approval token.

        SAFETY INVARIANT: MUST raise DeployPortError if approval_token is None
        or is not a recognised valid CTO approval token. This is the final
        defense-in-depth check; there is no execution path that bypasses it.

        Args:
            plan:           The deployment plan to execute.
            approval_token: A valid CTO approval token. None → immediate refusal.

        Returns:
            DeployResult with plan_id, target_env, status, executed_at.

        Raises:
            DeployPortError: if approval_token is None, invalid, or the
                deployment operation fails.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# InMemory implementation (for unit tests)
# ---------------------------------------------------------------------------


class InMemoryDeployPort(DeployPort):
    """Configurable in-memory stub for unit tests (ADR-081 / I-10: no real CI/CD).

    Seed valid tokens at construction. Pass ``fail_on_call=True`` to make every
    method raise :class:`DeployPortError` — exercises the HALT_PROVIDER_ERROR branch
    in DeployAgent.
    """

    def __init__(
        self,
        *,
        valid_tokens: set[str] | None = None,
        fail_on_call: bool = False,
    ) -> None:
        self._valid_tokens: set[str] = (
            valid_tokens if valid_tokens is not None else {"cto-valid-token"}
        )
        self._fail = fail_on_call

    def _check_fail(self) -> None:
        if self._fail:
            raise DeployPortError("InMemoryDeployPort configured to fail")

    async def prepare_deployment(self, target_env: DeployEnv) -> DeploymentPlan:
        self._check_fail()
        return DeploymentPlan(
            plan_id=f"plan-{target_env}-001",
            target_env=target_env,
            artifact_ref="sha256:abc123dead",
            prepared_at="2026-06-11T00:00:00Z",
        )

    async def request_approval(self, plan: DeploymentPlan) -> ApprovalRequest:
        self._check_fail()
        return ApprovalRequest(
            plan_id=plan.plan_id,
            target_env=plan.target_env,
            requested_at="2026-06-11T00:00:01Z",
        )

    async def execute_deployment(
        self,
        plan: DeploymentPlan,
        approval_token: str | None,
    ) -> DeployResult:
        self._check_fail()
        if approval_token is None:
            raise DeployPortError("approval required: approval_token must not be None")
        if approval_token not in self._valid_tokens:
            raise DeployPortError("invalid token: approval_token not recognised")
        return DeployResult(
            plan_id=plan.plan_id,
            target_env=plan.target_env,
            status="DEPLOYED",
            executed_at="2026-06-11T00:01:00Z",
        )


__all__ = [
    "ApprovalRequest",
    "DeployEnv",
    "DeployPort",
    "DeployPortError",
    "DeployResult",
    "DeploymentPlan",
    "InMemoryDeployPort",
]
