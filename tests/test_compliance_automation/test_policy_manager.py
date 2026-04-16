"""tests/test_compliance_automation/test_policy_manager.py — PolicyManager tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from services.compliance_automation.models import (
    InMemoryPolicyStore,
    PolicyStatus,
    PolicyVersion,
)
from services.compliance_automation.policy_manager import PolicyManager


@pytest.fixture
def manager():
    return PolicyManager(InMemoryPolicyStore())


@pytest.mark.asyncio
async def test_create_policy_returns_draft(manager):
    v = await manager.create_policy("pol-1", "content", "alice")
    assert v.status == PolicyStatus.DRAFT
    assert v.policy_id == "pol-1"
    assert v.version_number == 1
    assert v.author == "alice"
    assert v.approved_at is None


@pytest.mark.asyncio
async def test_create_policy_has_uuid_version_id(manager):
    v = await manager.create_policy("pol-1", "content", "alice")
    assert len(v.version_id) == 36


@pytest.mark.asyncio
async def test_submit_for_review(manager):
    v = await manager.create_policy("pol-1", "content", "alice")
    reviewed = await manager.submit_for_review(v.version_id)
    assert reviewed.status == PolicyStatus.REVIEW


@pytest.mark.asyncio
async def test_submit_for_review_missing_version(manager):
    with pytest.raises(ValueError, match="not found"):
        await manager.submit_for_review("nonexistent-id")


@pytest.mark.asyncio
async def test_approve_policy(manager):
    v = await manager.create_policy("pol-1", "content", "alice")
    reviewed = await manager.submit_for_review(v.version_id)
    approved = await manager.approve_policy(reviewed.version_id, "bob")
    assert approved.status == PolicyStatus.ACTIVE
    assert approved.approved_at is not None


@pytest.mark.asyncio
async def test_approve_policy_missing_version(manager):
    with pytest.raises(ValueError, match="not found"):
        await manager.approve_policy("nonexistent-id", "bob")


@pytest.mark.asyncio
async def test_retire_policy(manager):
    v = await manager.create_policy("pol-1", "content", "alice")
    reviewed = await manager.submit_for_review(v.version_id)
    approved = await manager.approve_policy(reviewed.version_id, "bob")
    retired = await manager.retire_policy(approved.version_id)
    assert retired.status == PolicyStatus.RETIRED


@pytest.mark.asyncio
async def test_retire_policy_missing_version(manager):
    with pytest.raises(ValueError, match="not found"):
        await manager.retire_policy("nonexistent-id")


@pytest.mark.asyncio
async def test_full_lifecycle(manager):
    v = await manager.create_policy("pol-full", "policy text", "author")
    assert v.status == PolicyStatus.DRAFT
    v2 = await manager.submit_for_review(v.version_id)
    assert v2.status == PolicyStatus.REVIEW
    v3 = await manager.approve_policy(v2.version_id, "approver")
    assert v3.status == PolicyStatus.ACTIVE
    v4 = await manager.retire_policy(v3.version_id)
    assert v4.status == PolicyStatus.RETIRED


@pytest.mark.asyncio
async def test_get_policy_history_sorted(manager):
    store = InMemoryPolicyStore()
    mgr = PolicyManager(store)
    await mgr.create_policy("pol-1", "v1 content", "alice")
    await store.save_version(
        PolicyVersion(
            version_id=str(uuid4()),
            policy_id="pol-1",
            version_number=2,
            content="v2 content",
            status=PolicyStatus.DRAFT,
            author="bob",
            created_at=datetime.now(UTC),
        )
    )
    history = await mgr.get_policy_history("pol-1")
    assert len(history) == 2
    assert history[0].version_number == 1
    assert history[1].version_number == 2


@pytest.mark.asyncio
async def test_diff_versions_changed(manager):
    store = InMemoryPolicyStore()
    mgr = PolicyManager(store)
    await mgr.create_policy("pol-1", "content A", "alice")
    await store.save_version(
        PolicyVersion(
            version_id=str(uuid4()),
            policy_id="pol-1",
            version_number=2,
            content="content B",
            status=PolicyStatus.REVIEW,
            author="bob",
            created_at=datetime.now(UTC),
        )
    )
    diff = await mgr.diff_versions("pol-1", 1, 2)
    assert diff["policy_id"] == "pol-1"
    assert diff["v1"] == 1
    assert diff["v2"] == 2
    assert diff["v1_content"] == "content A"
    assert diff["v2_content"] == "content B"
    assert diff["changed"] is True


@pytest.mark.asyncio
async def test_diff_versions_unchanged(manager):
    store = InMemoryPolicyStore()
    mgr = PolicyManager(store)
    await mgr.create_policy("pol-same", "same content", "alice")
    await store.save_version(
        PolicyVersion(
            version_id=str(uuid4()),
            policy_id="pol-same",
            version_number=2,
            content="same content",
            status=PolicyStatus.REVIEW,
            author="bob",
            created_at=datetime.now(UTC),
        )
    )
    diff = await mgr.diff_versions("pol-same", 1, 2)
    assert diff["changed"] is False


@pytest.mark.asyncio
async def test_diff_versions_missing_v1_raises(manager):
    await manager.create_policy("pol-1", "content", "alice")
    with pytest.raises(ValueError, match="Version 99 not found"):
        await manager.diff_versions("pol-1", 99, 1)


@pytest.mark.asyncio
async def test_diff_versions_missing_v2_raises(manager):
    await manager.create_policy("pol-1", "content", "alice")
    with pytest.raises(ValueError, match="Version 99 not found"):
        await manager.diff_versions("pol-1", 1, 99)


@pytest.mark.asyncio
async def test_create_policy_preserves_content(manager):
    v = await manager.create_policy("pol-content", "my policy text", "author")
    assert v.content == "my policy text"


@pytest.mark.asyncio
async def test_approved_at_is_none_before_approval(manager):
    v = await manager.create_policy("pol-1", "content", "alice")
    reviewed = await manager.submit_for_review(v.version_id)
    assert reviewed.approved_at is None
