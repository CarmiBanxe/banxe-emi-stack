"""CLI script extension tests for S16.7 — real-API path."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

import pytest

from services.ci_governance.factory import (
    get_protection_reader,
    get_real_gh_protection_reader,
)
from services.ci_governance.gh_api_protection_reader import (
    GitHubApiProtectionReader,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "ci-protection-drift-check.py"

_BASELINE = {
    "required_status_checks": {
        "strict": True,
        "checks": [{"context": "Smoke Gate (mock tier)"}],
    },
    "enforce_admins": False,
    "required_pull_request_reviews": None,
    "restrictions": None,
}


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_ci_drift_script_s16_7", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_ci_drift_script_s16_7"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _clean_env_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        "CI_GOVERNANCE_GH_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "CI_GOVERNANCE_READER_MODE",
    ):
        monkeypatch.delenv(k, raising=False)
    get_protection_reader.cache_clear()
    get_real_gh_protection_reader.cache_clear()
    yield
    get_protection_reader.cache_clear()
    get_real_gh_protection_reader.cache_clear()


def _write_baseline(tmp_path: Path) -> Path:
    p = tmp_path / "baseline.json"
    p.write_text(json.dumps(_BASELINE), encoding="utf-8")
    return p


class _FakeHttpClient:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls: list[tuple[str, dict, str]] = []

    def __call__(self, url: str, headers: dict[str, str], method: str) -> tuple[int, bytes]:
        self.calls.append((url, dict(headers), method))
        return 200, self.body


def _install_fake_real_reader(
    monkeypatch: pytest.MonkeyPatch, body: dict[str, Any]
) -> _FakeHttpClient:
    """Replace the lru_cached real-API reader with one wired to a fake HTTP."""
    fake = _FakeHttpClient(json.dumps(body).encode("utf-8"))
    import services.ci_governance.factory as factory_mod

    def _fake_factory() -> GitHubApiProtectionReader:
        return GitHubApiProtectionReader(
            owner="CarmiBanxe",
            repo="banxe-emi-stack",
            token_provider=lambda: "tok-x",
            branch="main",
            http_client=fake,
        )

    monkeypatch.setattr(factory_mod, "get_real_gh_protection_reader", _fake_factory)
    return fake


def test_script_uses_gh_api_reader_when_token_present_and_no_dry_run_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline = _write_baseline(tmp_path)
    monkeypatch.setenv("CI_GOVERNANCE_GH_TOKEN", "tok-x")
    fake = _install_fake_real_reader(
        monkeypatch,
        {
            "required_status_checks": {
                "strict": True,
                "checks": [{"context": "Smoke Gate (mock tier)"}],
            },
            "enforce_admins": {"enabled": False},
        },
    )
    mod = _load_script()
    rc = mod.main(["--baseline", str(baseline)])
    out = capsys.readouterr().out
    result = json.loads(out.strip())
    assert rc == 0
    assert result["drift_detected"] is False
    # FakeHttpClient confirms the real-API reader was actually used.
    assert fake.calls, "real-API reader was not invoked"
    assert fake.calls[0][2] == "GET"


def test_script_still_exits_2_when_no_token_and_no_dry_run_payload(
    tmp_path: Path,
) -> None:
    baseline = _write_baseline(tmp_path)
    mod = _load_script()
    rc = mod.main(["--baseline", str(baseline)])
    assert rc == 2


def test_script_force_real_api_flag_bypasses_in_memory_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline = _write_baseline(tmp_path)
    # A captured payload that WOULD report no drift if used.
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(
        json.dumps(
            {
                "required_status_checks": {
                    "strict": True,
                    "checks": [{"context": "Smoke Gate (mock tier)"}],
                },
                "enforce_admins": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )

    # Real-API would say DRIFT (missing the required Smoke Gate context).
    monkeypatch.setenv("CI_GOVERNANCE_GH_TOKEN", "tok-x")
    fake = _install_fake_real_reader(
        monkeypatch,
        {
            "required_status_checks": {"strict": True, "checks": []},
            "enforce_admins": {"enabled": False},
        },
    )

    mod = _load_script()
    rc = mod.main(
        [
            "--baseline",
            str(baseline),
            "--dry-run-payload",
            str(payload_file),
            "--force-real-api",
        ]
    )
    out = capsys.readouterr().out
    result = json.loads(out.strip())
    # Real-API drove the comparison (not the local payload), so drift IS detected.
    assert rc == 1
    assert result["drift_detected"] is True
    assert "Smoke Gate (mock tier)" in result["missing_contexts"]
    assert fake.calls, "real-API was not invoked under --force-real-api"
