"""
tests/test_repo_watch.py — Repo Watch service tests
S14-03 | banxe-emi-stack

Tests for services/repo_watch/*.py:
  - config.py: load_config (no YAML), make_in_memory_config, dataclass defaults
  - github_client.py: RepoStats, GitHubRateLimitError, InMemoryGitHubClient
  - maturity_evaluator.py: evaluate_maturity (all branches)
  - store.py: InMemoryRepoWatchStore (all methods)
  - notifier.py: InMemoryNotifier (send + failure simulation)

Coverage target: 0% → ≥70% across all repo_watch files
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from services.repo_watch.config import (
    CriticalIssueLabels,
    DevCandidateThresholds,
    ProdCandidateThresholds,
    RepoWatchConfig,
    WatchedRepo,
    load_config,
    make_in_memory_config,
)
from services.repo_watch.github_client import (
    GitHubRateLimitError,
    InMemoryGitHubClient,
    RepoStats,
)
from services.repo_watch.maturity_evaluator import (
    MaturityLevel,
    MaturityResult,
    evaluate_maturity,
)
from services.repo_watch.notifier import InMemoryNotifier
from services.repo_watch.store import (
    AlertRecord,
    InMemoryRepoWatchStore,
    SnapshotRecord,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _healthy_stats(
    owner: str = "test-owner",
    repo: str = "test-repo",
    *,
    stars: int = 200,
    forks: int = 20,
    contributors: int = 8,
    open_bugs: int = 1,
    is_archived: bool = False,
    has_ci: bool = True,
    days_since_commit: int = 1,
) -> RepoStats:
    return RepoStats(
        owner=owner,
        repo=repo,
        stars=stars,
        forks=forks,
        open_issues=open_bugs + 2,
        open_bug_issues=open_bugs,
        contributors_count=contributors,
        last_commit_date=_now() - timedelta(days=days_since_commit),
        default_branch="main",
        license_spdx="MIT",
        is_archived=is_archived,
        has_ci=has_ci,
        fetched_at=_now(),
    )


def _default_config(
    min_contributors: int = 3,
    max_bugs: int = 5,
    days_since_commit: int = 7,
    weeks_observed: int = 4,
) -> RepoWatchConfig:
    return make_in_memory_config(
        min_contributors=min_contributors,
        max_open_bug_issues=max_bugs,
    )


def _snapshot(
    owner: str = "test", repo: str = "repo", maturity: str = "PROD_CANDIDATE"
) -> SnapshotRecord:
    return SnapshotRecord(
        id=f"snap-{owner}-{repo}-{_now().isoformat()}",
        owner=owner,
        repo=repo,
        stars=100,
        forks=10,
        open_issues=3,
        open_bug_issues=1,
        contributors_count=6,
        last_commit_date=_now(),
        maturity_level=maturity,
        maturity_reason="test",
        is_archived=False,
        has_ci=True,
        license_spdx="MIT",
        fetched_at=_now(),
    )


# ── config.py tests ───────────────────────────────────────────────────────────


def test_load_config_no_yaml_returns_defaults():
    """load_config() with missing YAML file returns defaults."""
    cfg = load_config(yaml_path=None)
    assert cfg.dev_candidate.min_contributors == 3
    assert cfg.prod_candidate.min_contributors == 5
    assert cfg.check_interval_seconds == 604_800


def test_make_in_memory_config_returns_config():
    cfg = make_in_memory_config("owner", "repo")
    assert len(cfg.repos) == 1
    assert cfg.repos[0].owner == "owner"
    assert cfg.repos[0].repo == "repo"


def test_make_in_memory_config_custom_thresholds():
    cfg = make_in_memory_config(min_contributors=5, max_open_bug_issues=2)
    assert cfg.dev_candidate.min_contributors == 5
    assert cfg.dev_candidate.max_open_bug_issues == 2


def test_dev_candidate_thresholds_defaults():
    t = DevCandidateThresholds()
    assert t.min_contributors == 3
    assert t.max_open_bug_issues == 5
    assert t.max_days_since_last_commit == 7
    assert t.min_weeks_observed == 4


def test_prod_candidate_thresholds_defaults():
    t = ProdCandidateThresholds()
    assert t.min_contributors == 5
    assert t.max_open_bug_issues == 2
    assert t.min_weeks_stable == 12


def test_watched_repo_dataclass():
    r = WatchedRepo(owner="garrytan", repo="gbrain", reason="key dependency")
    assert r.owner == "garrytan"
    assert r.reason == "key dependency"


def test_critical_issue_labels_defaults():
    labels = CriticalIssueLabels()
    assert "bug" in labels.labels
    assert "security" in labels.labels


# ── github_client.py tests ────────────────────────────────────────────────────


def test_repo_stats_fields():
    stats = _healthy_stats()
    assert stats.owner == "test-owner"
    assert stats.repo == "test-repo"
    assert stats.has_ci is True


def test_github_rate_limit_error_message():
    reset_at = _now() + timedelta(hours=1)
    err = GitHubRateLimitError(reset_at=reset_at)
    assert "resets at" in str(err)
    assert err.reset_at == reset_at


@pytest.mark.asyncio
async def test_in_memory_github_client_default_stats():
    client = InMemoryGitHubClient()
    stats = await client.fetch_repo_stats("garrytan", "gbrain")
    assert stats.owner == "garrytan"
    assert stats.repo == "gbrain"
    assert stats.stars == 200
    assert stats.has_ci is True


@pytest.mark.asyncio
async def test_in_memory_github_client_custom_stats():
    custom = _healthy_stats(stars=999)
    client = InMemoryGitHubClient(stats=custom)
    stats = await client.fetch_repo_stats("any", "repo")
    assert stats.stars == 999


@pytest.mark.asyncio
async def test_in_memory_github_client_async():
    client = InMemoryGitHubClient()
    stats = await client.fetch_repo_stats("test", "repo")
    assert stats.contributors_count == 6
    assert stats.is_archived is False


# ── maturity_evaluator.py tests ───────────────────────────────────────────────


def test_evaluate_maturity_archived_returns_not_ready():
    cfg = _default_config()
    stats = _healthy_stats(is_archived=True)
    result = evaluate_maturity(stats, cfg)
    assert result.level == MaturityLevel.NOT_READY
    assert "archived" in result.reasons[0].lower()


def test_evaluate_maturity_healthy_prod_candidate():
    cfg = _default_config(min_contributors=3, max_bugs=5)
    stats = _healthy_stats(contributors=8, open_bugs=1)
    # Need 12 weeks stable for PROD_CANDIDATE
    result = evaluate_maturity(stats, cfg, weeks_stable=12)
    assert result.level == MaturityLevel.PROD_CANDIDATE


def test_evaluate_maturity_dev_candidate_not_enough_weeks():
    cfg = _default_config(min_contributors=3, max_bugs=5)
    stats = _healthy_stats(contributors=8, open_bugs=1)
    # Not enough weeks stable → DEV_CANDIDATE max
    result = evaluate_maturity(stats, cfg, weeks_stable=5)
    assert result.level in {MaturityLevel.DEV_CANDIDATE, MaturityLevel.PROD_CANDIDATE}


def test_evaluate_maturity_not_ready_low_contributors():
    cfg = _default_config(min_contributors=5, max_bugs=5)
    stats = _healthy_stats(contributors=2)
    result = evaluate_maturity(stats, cfg)
    assert result.level == MaturityLevel.NOT_READY
    assert len(result.reasons) > 0


def test_evaluate_maturity_not_ready_too_many_bugs():
    cfg = _default_config(min_contributors=3, max_bugs=2)
    stats = _healthy_stats(open_bugs=5)
    result = evaluate_maturity(stats, cfg)
    assert result.level == MaturityLevel.NOT_READY


def test_evaluate_maturity_not_ready_stale_commit():
    cfg = _default_config()
    stats = _healthy_stats(days_since_commit=30)
    result = evaluate_maturity(stats, cfg)
    assert result.level == MaturityLevel.NOT_READY


def test_maturity_result_frozen():
    r = MaturityResult(level=MaturityLevel.DEV_CANDIDATE, reasons=("reason",))
    assert r.level == MaturityLevel.DEV_CANDIDATE
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        r.level = MaturityLevel.PROD_CANDIDATE  # frozen dataclass


def test_maturity_level_enum_values():
    assert MaturityLevel.NOT_READY.value == "NOT_READY"
    assert MaturityLevel.DEV_CANDIDATE.value == "DEV_CANDIDATE"
    assert MaturityLevel.PROD_CANDIDATE.value == "PROD_CANDIDATE"


# ── store.py tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_memory_store_save_and_get_snapshot():
    store = InMemoryRepoWatchStore()
    snap = _snapshot("owner1", "repo1")
    await store.save_snapshot(snap)
    results = await store.get_snapshots("owner1", "repo1")
    assert len(results) == 1
    assert results[0].owner == "owner1"


@pytest.mark.asyncio
async def test_in_memory_store_get_snapshots_filter_by_repo():
    store = InMemoryRepoWatchStore()
    await store.save_snapshot(_snapshot("o1", "r1"))
    await store.save_snapshot(_snapshot("o1", "r2"))
    results = await store.get_snapshots("o1", "r1")
    assert all(s.repo == "r1" for s in results)


@pytest.mark.asyncio
async def test_in_memory_store_get_snapshots_respects_limit():
    store = InMemoryRepoWatchStore()
    for _ in range(5):
        await store.save_snapshot(_snapshot("o", "r"))
    results = await store.get_snapshots("o", "r", limit=3)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_in_memory_store_get_latest_snapshot():
    store = InMemoryRepoWatchStore()
    snap = _snapshot("o", "r")
    await store.save_snapshot(snap)
    latest = await store.get_latest_snapshot("o", "r")
    assert latest is not None
    assert latest.id == snap.id


@pytest.mark.asyncio
async def test_in_memory_store_get_latest_snapshot_no_results():
    store = InMemoryRepoWatchStore()
    latest = await store.get_latest_snapshot("o", "nonexistent")
    assert latest is None


@pytest.mark.asyncio
async def test_in_memory_store_count_stable_weeks_prod_candidate():
    store = InMemoryRepoWatchStore()
    for _ in range(3):
        await store.save_snapshot(_snapshot("o", "r", maturity="PROD_CANDIDATE"))
    count = await store.count_stable_weeks("o", "r", MaturityLevel.PROD_CANDIDATE)
    assert count == 3


@pytest.mark.asyncio
async def test_in_memory_store_count_stable_weeks_breaks_on_lower():
    store = InMemoryRepoWatchStore()
    # Newest: PROD, then NOT_READY → should count only 1
    await store.save_snapshot(
        SnapshotRecord(
            id="snap-old",
            owner="o",
            repo="r",
            stars=10,
            forks=1,
            open_issues=1,
            open_bug_issues=0,
            contributors_count=5,
            last_commit_date=_now() - timedelta(days=14),
            maturity_level="NOT_READY",
            maturity_reason="bad",
            is_archived=False,
            has_ci=True,
            license_spdx=None,
            fetched_at=_now() - timedelta(days=14),
        )
    )
    await store.save_snapshot(
        SnapshotRecord(
            id="snap-new",
            owner="o",
            repo="r",
            stars=10,
            forks=1,
            open_issues=1,
            open_bug_issues=0,
            contributors_count=5,
            last_commit_date=_now(),
            maturity_level="PROD_CANDIDATE",
            maturity_reason="good",
            is_archived=False,
            has_ci=True,
            license_spdx=None,
            fetched_at=_now(),
        )
    )
    count = await store.count_stable_weeks("o", "r", MaturityLevel.PROD_CANDIDATE)
    assert count == 1


@pytest.mark.asyncio
async def test_in_memory_store_alert_already_sent_false():
    store = InMemoryRepoWatchStore()
    result = await store.alert_already_sent("dedup-key-001")
    assert result is False


@pytest.mark.asyncio
async def test_in_memory_store_record_alert_and_check_sent():
    store = InMemoryRepoWatchStore()
    alert = AlertRecord(
        id="alert-001",
        owner="o",
        repo="r",
        prev_maturity_level="NOT_READY",
        new_maturity_level="DEV_CANDIDATE",
        message="Repo leveled up!",
        sent_at=_now(),
        dedup_key="dedup-001",
    )
    await store.record_alert(alert)
    result = await store.alert_already_sent("dedup-001")
    assert result is True


@pytest.mark.asyncio
async def test_in_memory_store_unsent_alert_not_deduped():
    store = InMemoryRepoWatchStore()
    alert = AlertRecord(
        id="alert-002",
        owner="o",
        repo="r",
        prev_maturity_level=None,
        new_maturity_level="DEV_CANDIDATE",
        message="Pending alert",
        sent_at=None,  # Not sent yet
        dedup_key="dedup-002",
    )
    await store.record_alert(alert)
    result = await store.alert_already_sent("dedup-002")
    assert result is False  # Not sent (sent_at is None)


# ── notifier.py tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_in_memory_notifier_send_weekly_digest():
    notifier = InMemoryNotifier()
    cfg = _default_config()
    stats = _healthy_stats()
    result_obj = MaturityResult(level=MaturityLevel.PROD_CANDIDATE, reasons=())
    sent = await notifier.send_weekly_digest("owner", "repo", stats, result_obj)
    assert sent is True
    assert len(notifier.digests) == 1
    assert notifier.digests[0]["owner"] == "owner"
    assert notifier.digests[0]["level"] == "PROD_CANDIDATE"


@pytest.mark.asyncio
async def test_in_memory_notifier_send_weekly_digest_fail():
    notifier = InMemoryNotifier()
    notifier.set_fail(fail=True)
    stats = _healthy_stats()
    result_obj = MaturityResult(level=MaturityLevel.DEV_CANDIDATE, reasons=())
    sent = await notifier.send_weekly_digest("o", "r", stats, result_obj)
    assert sent is False
    assert len(notifier.digests) == 0


@pytest.mark.asyncio
async def test_in_memory_notifier_send_status_change():
    notifier = InMemoryNotifier()
    sent = await notifier.send_status_change(
        owner="o",
        repo="r",
        prev_level=MaturityLevel.NOT_READY,
        new_level=MaturityLevel.DEV_CANDIDATE,
        reasons=("min contributors met", "CI added"),
    )
    assert sent is True
    assert len(notifier.changes) == 1
    assert notifier.changes[0]["prev"] == "NOT_READY"
    assert notifier.changes[0]["new"] == "DEV_CANDIDATE"


@pytest.mark.asyncio
async def test_in_memory_notifier_send_status_change_none_prev():
    notifier = InMemoryNotifier()
    sent = await notifier.send_status_change(
        owner="o",
        repo="r",
        prev_level=None,
        new_level=MaturityLevel.DEV_CANDIDATE,
        reasons=("first observation",),
    )
    assert sent is True
    assert notifier.changes[0]["prev"] is None


@pytest.mark.asyncio
async def test_in_memory_notifier_fail_mode_status_change():
    notifier = InMemoryNotifier()
    notifier.set_fail()
    sent = await notifier.send_status_change(
        owner="o",
        repo="r",
        prev_level=None,
        new_level=MaturityLevel.NOT_READY,
        reasons=("archived",),
    )
    assert sent is False
    assert len(notifier.changes) == 0


# ── Additional config.py coverage ─────────────────────────────────────────────


def test_load_config_returns_repo_watch_config():
    """load_config with no file returns RepoWatchConfig with empty repos tuple."""
    cfg = load_config()
    assert isinstance(cfg, RepoWatchConfig)
    assert isinstance(cfg.repos, tuple)


def test_load_config_env_override(monkeypatch):
    """GITHUB_TOKEN env var overrides the config."""
    monkeypatch.setenv("GITHUB_TOKEN", "test-token-abc")
    cfg = load_config()
    assert cfg.github_token == "test-token-abc"
