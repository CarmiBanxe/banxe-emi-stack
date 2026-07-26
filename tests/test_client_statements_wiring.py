"""tests/test_client_statements_wiring.py — build_statement_client_agent() tests.

Proves the fail-loud contract: refuses to build a live agent from the shipped
PROPOSED policy, and succeeds once a policy is ACTIVE and fully configured.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.agents.statement_agent import StatementClientAgent
from services.client_statements.statement_port import DeliveryChannel
from services.client_statements.wiring import build_statement_client_agent
from services.shared.mask_policy import MaskPolicyNotReady

REPO_ROOT = Path(__file__).resolve().parent.parent
SHIPPED_STATEMENTS_POLICY = REPO_ROOT / "config" / "masks" / "statements-mask-policy.yaml"

_ACTIVE_POLICY_YAML = """
schema: statements-mask-policy/v1
mask_id: statements
status: ACTIVE
cost_cap:
  window: 24h
  currency: GBP
  max_tokens_window: 200000
  max_cost_window: "5.00"
  max_request_tokens: 20000
  max_request_cost: "0.50"
confidence_bands:
  auto_min_confidence: 0.9
  review_min_confidence: 0.7
delivery_channel_classification:
  IN_APP: AUTO
  EMAIL: REVIEW
  EXPORT: REVIEW
escalation_roles:
  pii_compliance_block: dpo
  data_egress_review: dpo
"""


def test_shipped_proposed_policy_refuses_to_build_live_agent() -> None:
    with pytest.raises(MaskPolicyNotReady) as exc_info:
        build_statement_client_agent(policy_path=SHIPPED_STATEMENTS_POLICY)
    assert exc_info.value.code == "mask_policy_not_active"


def test_active_fully_configured_policy_builds_a_real_agent(tmp_path: Path) -> None:
    active_policy = tmp_path / "active.yaml"
    active_policy.write_text(_ACTIVE_POLICY_YAML, encoding="utf-8")

    agent = build_statement_client_agent(policy_path=active_policy)

    assert isinstance(agent, StatementClientAgent)
    mask = agent._mask  # noqa: SLF001 - test-only introspection of the assembled mask
    assert mask.auto_threshold == 0.9
    assert mask.review_floor == 0.7
    assert mask.dpo_role == "dpo"
    assert mask.egress_role == "dpo"
    assert mask.in_boundary_channels == (DeliveryChannel.IN_APP,)
    assert mask.cost_cap.max_window_tokens == 200000
    assert mask.cost_cap.max_request_tokens == 20000
