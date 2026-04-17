"""
tests/test_referral/test_campaign_manager.py — Unit tests for CampaignManager
IL-REF-01 | Phase 30 | banxe-emi-stack
"""

from __future__ import annotations

import pytest

from services.referral.campaign_manager import CampaignManager
from services.referral.models import InMemoryReferralCampaignStore


@pytest.fixture()
def manager() -> CampaignManager:
    return CampaignManager()


def _create_draft(manager: CampaignManager, name: str = "Test Campaign") -> dict:
    return manager.create_campaign(
        name=name,
        referrer_reward_str="25.00",
        referee_reward_str="10.00",
        total_budget_str="10000.00",
    )


# ── create_campaign ────────────────────────────────────────────────────────


def test_create_campaign_returns_campaign_id(manager: CampaignManager) -> None:
    result = _create_draft(manager)
    assert result["campaign_id"] != ""


def test_create_campaign_status_is_draft(manager: CampaignManager) -> None:
    result = _create_draft(manager)
    assert result["status"] == "DRAFT"


def test_create_campaign_has_correct_rewards(manager: CampaignManager) -> None:
    result = _create_draft(manager)
    assert result["referrer_reward"] == "25.00"
    assert result["referee_reward"] == "10.00"


def test_create_campaign_has_correct_budget(manager: CampaignManager) -> None:
    result = _create_draft(manager)
    assert result["total_budget"] == "10000.00"


def test_create_campaign_zero_referrer_reward_raises(manager: CampaignManager) -> None:
    with pytest.raises(ValueError, match="referrer_reward must be > 0"):
        manager.create_campaign("Test", "0", "10.00", "1000.00")


def test_create_campaign_negative_referrer_reward_raises(manager: CampaignManager) -> None:
    with pytest.raises(ValueError, match="referrer_reward must be > 0"):
        manager.create_campaign("Test", "-5", "10.00", "1000.00")


def test_create_campaign_zero_referee_reward_raises(manager: CampaignManager) -> None:
    with pytest.raises(ValueError, match="referee_reward must be > 0"):
        manager.create_campaign("Test", "25.00", "0", "1000.00")


def test_create_campaign_zero_budget_raises(manager: CampaignManager) -> None:
    with pytest.raises(ValueError, match="total_budget must be > 0"):
        manager.create_campaign("Test", "25.00", "10.00", "0")


def test_create_campaign_saves_to_store() -> None:
    store = InMemoryReferralCampaignStore()
    mgr = CampaignManager(campaign_store=store)
    result = mgr.create_campaign("Saved", "10.00", "5.00", "500.00")
    assert store.get(result["campaign_id"]) is not None


# ── activate_campaign ──────────────────────────────────────────────────────


def test_activate_campaign_draft_to_active(manager: CampaignManager) -> None:
    result = _create_draft(manager)
    activated = manager.activate_campaign(result["campaign_id"])
    assert activated["status"] == "ACTIVE"


def test_activate_campaign_not_found_raises(manager: CampaignManager) -> None:
    with pytest.raises(ValueError, match="Campaign not found"):
        manager.activate_campaign("nonexistent-id")


def test_activate_campaign_non_draft_raises(manager: CampaignManager) -> None:
    result = _create_draft(manager)
    camp_id = result["campaign_id"]
    manager.activate_campaign(camp_id)
    with pytest.raises(ValueError, match="Can only activate DRAFT"):
        manager.activate_campaign(camp_id)


# ── pause_campaign ─────────────────────────────────────────────────────────


def test_pause_campaign_active_to_paused(manager: CampaignManager) -> None:
    result = _create_draft(manager)
    camp_id = result["campaign_id"]
    manager.activate_campaign(camp_id)
    paused = manager.pause_campaign(camp_id)
    assert paused["status"] == "PAUSED"


def test_pause_campaign_not_found_raises(manager: CampaignManager) -> None:
    with pytest.raises(ValueError, match="Campaign not found"):
        manager.pause_campaign("nonexistent-id")


def test_pause_campaign_non_active_raises(manager: CampaignManager) -> None:
    result = _create_draft(manager)
    camp_id = result["campaign_id"]
    with pytest.raises(ValueError, match="Can only pause ACTIVE"):
        manager.pause_campaign(camp_id)


# ── end_campaign ───────────────────────────────────────────────────────────


def test_end_campaign_from_active(manager: CampaignManager) -> None:
    result = _create_draft(manager)
    camp_id = result["campaign_id"]
    manager.activate_campaign(camp_id)
    ended = manager.end_campaign(camp_id)
    assert ended["status"] == "ENDED"


def test_end_campaign_from_draft(manager: CampaignManager) -> None:
    result = _create_draft(manager)
    ended = manager.end_campaign(result["campaign_id"])
    assert ended["status"] == "ENDED"


def test_end_campaign_already_ended_raises(manager: CampaignManager) -> None:
    result = _create_draft(manager)
    camp_id = result["campaign_id"]
    manager.end_campaign(camp_id)
    with pytest.raises(ValueError, match="already ended"):
        manager.end_campaign(camp_id)


def test_end_campaign_not_found_raises(manager: CampaignManager) -> None:
    with pytest.raises(ValueError, match="Campaign not found"):
        manager.end_campaign("nonexistent-id")


# ── get_campaign_stats ─────────────────────────────────────────────────────


def test_get_campaign_stats_default_campaign(manager: CampaignManager) -> None:
    result = manager.get_campaign_stats("camp-default")
    assert result["campaign_id"] == "camp-default"


def test_get_campaign_stats_remaining_budget(manager: CampaignManager) -> None:
    result = manager.get_campaign_stats("camp-default")
    # Default: total=100000, spent=0 → remaining=100000
    assert result["remaining_budget"] == "100000.00"


def test_get_campaign_stats_not_found_raises(manager: CampaignManager) -> None:
    with pytest.raises(ValueError, match="Campaign not found"):
        manager.get_campaign_stats("nonexistent-id")


def test_get_campaign_stats_has_all_fields(manager: CampaignManager) -> None:
    result = manager.get_campaign_stats("camp-default")
    assert "referrer_reward" in result
    assert "referee_reward" in result
    assert "total_budget" in result
    assert "spent_budget" in result


# ── list_active_campaigns ──────────────────────────────────────────────────


def test_list_active_campaigns_includes_default(manager: CampaignManager) -> None:
    result = manager.list_active_campaigns()
    ids = [c["campaign_id"] for c in result["campaigns"]]
    assert "camp-default" in ids


def test_list_active_campaigns_excludes_draft(manager: CampaignManager) -> None:
    draft = _create_draft(manager, name="Draft Only")
    result = manager.list_active_campaigns()
    ids = [c["campaign_id"] for c in result["campaigns"]]
    assert draft["campaign_id"] not in ids


def test_list_active_campaigns_after_activation(manager: CampaignManager) -> None:
    draft = _create_draft(manager, name="Newly Active")
    manager.activate_campaign(draft["campaign_id"])
    result = manager.list_active_campaigns()
    ids = [c["campaign_id"] for c in result["campaigns"]]
    assert draft["campaign_id"] in ids
