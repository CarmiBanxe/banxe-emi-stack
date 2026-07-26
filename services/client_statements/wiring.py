"""services/client_statements/wiring.py — assembles a real StatementClientAgent.

WHY THIS FILE EXISTS
--------------------
`StatementClientAgent` (services/agents/statement_agent.py) needs a `StatementPort`,
a `DecisionRecorder`, and a `StatementMask` (config-as-data — cost caps, confidence
bands, escalation roles, channel classification). Nothing assembled these together
before this patchset. This module is that assembly point ONLY — it contains no
governance logic of its own (that's the client agent) and no domain logic of its own
(that's the adapter); it just wires the three real pieces together from the
config-as-data substrate (services/shared/mask_policy.py, Option A) plus the new
adapter (statement_adapter.py, Option B step 1).

FAIL-LOUD CONTRACT (the actual point of this module)
------------------------------------------------------
`load_statements_mask_policy()` loads a `status: PROPOSED` policy successfully — that
is the correct, honest current state of `config/masks/statements-mask-policy.yaml`
(no operator/counsel values supplied yet). Loading successfully is NOT the same as
being safe to build a live agent from. This module enforces the additional rule:
`build_statement_client_agent()` refuses to construct anything unless the loaded
policy's `status` is ACTIVE (which, combined with the loader's own
`MaskPolicyNotReady` check, guarantees every required field is non-null before a
`StatementMask` is ever built).

NOT DONE HERE (deliberately)
-----------------------------
Nothing in this module is called by any live MCP tool or API route. Wiring
`banxe_mcp/server.py` / `api/routers/client_statements.py` to use this is a separate,
explicitly-approved step — see docs/API.md "Analytics / Statements Mask Config-as-Data
Substrate" for why, and what's required first.
"""

from __future__ import annotations

from pathlib import Path

from services.agents._lineage import CostCap as LineageCostCap
from services.agents._lineage import DecisionRecorder
from services.agents.recorders import get_decision_recorder
from services.agents.statement_agent import StatementClientAgent, StatementMask
from services.client_statements.statement_adapter import StatementAdapter
from services.client_statements.statement_generator import StatementGenerator
from services.client_statements.statement_port import DeliveryChannel
from services.shared.mask_policy import (
    DeliveryAction,
    MaskPolicyNotReady,
    MaskPolicyStatus,
    load_statements_mask_policy,
)


def build_statement_client_agent(
    *,
    policy_path: Path | None = None,
    generator: StatementGenerator | None = None,
    recorder: DecisionRecorder | None = None,
) -> StatementClientAgent:
    """Assemble a real StatementClientAgent wired to the governed StatementAdapter.

    Loads the operator/counsel-supplied config-as-data policy and refuses to build a
    live agent unless it is ACTIVE and fully configured. A `status: PROPOSED` policy
    (the shipped default) is not sufficient, even though `load_statements_mask_policy`
    loads it without error — loading and being production-ready are different checks.

    Args:
        policy_path: override path to the mask policy YAML (defaults to the
            canonical `config/masks/statements-mask-policy.yaml`).
        generator: optional `StatementGenerator` override (tests only).
        recorder: optional `DecisionRecorder` override; defaults to
            `get_decision_recorder()` (services/agents/recorders.py).

    Returns:
        A `StatementClientAgent` ready for real use.

    Raises:
        MaskPolicyFileNotFound: the policy YAML does not exist.
        MaskPolicySchemaError: the policy YAML is malformed.
        MaskPolicyNotReady: the policy's `status` is not ACTIVE, or is ACTIVE but a
            required field is still unset.
    """
    policy = load_statements_mask_policy(policy_path)
    if policy.status is not MaskPolicyStatus.ACTIVE:
        raise MaskPolicyNotReady(
            f"Statements mask policy status is {policy.status.value}, not ACTIVE — "
            "refusing to build a live StatementClientAgent from an unapproved policy. "
            "Supply real operator/counsel values in "
            "config/masks/statements-mask-policy.yaml and set status: ACTIVE first.",
            code="mask_policy_not_active",
        )

    channel_actions = {
        DeliveryChannel.IN_APP: policy.delivery_channel_classification.in_app,
        DeliveryChannel.EMAIL: policy.delivery_channel_classification.email,
        DeliveryChannel.EXPORT: policy.delivery_channel_classification.export,
    }
    in_boundary_channels = tuple(
        channel
        for channel, action in channel_actions.items()
        if action == DeliveryAction.AUTO
    )

    mask = StatementMask(
        cost_cap=LineageCostCap(
            max_request_tokens=policy.cost_cap.max_request_tokens,
            max_request_cost=policy.cost_cap.max_request_cost,
            max_window_tokens=policy.cost_cap.max_tokens_window,
            max_window_cost=policy.cost_cap.max_cost_window,
        ),
        auto_threshold=policy.confidence_bands.auto_min_confidence,
        review_floor=policy.confidence_bands.review_min_confidence,
        dpo_role=policy.escalation_roles.pii_compliance_block,
        egress_role=policy.escalation_roles.data_egress_review,
        in_boundary_channels=in_boundary_channels,
    )

    return StatementClientAgent(
        statement_port=StatementAdapter(generator=generator),
        recorder=recorder or get_decision_recorder(),
        mask=mask,
    )
