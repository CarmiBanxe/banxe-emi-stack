"""CLI script tests for S16.8 snapshot-capture."""

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
    get_snapshot_writer,
)
from services.ci_governance.gh_api_protection_reader import (
    GitHubApiProtectionReader,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "ci-protection-snapshot-capture.py"

_DEFAULT_SNAPSHOT_PATH = "/var/cache/banxe/last-protection-snapshot.json"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_snapshot_capture_script", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_snapshot_capture_script"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _clean_env_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        "CI_GOVERNANCE_GH_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "CI_GOVERNANCE_READER_MODE",
        "CI_GOVERNANCE_SNAPSHOT_PATH",
    ):
        monkeypatch.delenv(k, raising=False)
    get_protection_reader.cache_clear()
    get_real_gh_protection_reader.cache_clear()
    get_snapshot_writer.cache_clear()
    yield
    get_protection_reader.cache_clear()
    get_real_gh_protection_reader.cache_clear()
    get_snapshot_writer.cache_clear()


class _FakeHttp:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls: list[tuple[str, dict, str]] = []

    def __call__(self, url: str, headers: dict[str, str], method: str) -> tuple[int, bytes]:
        self.calls.append((url, dict(headers), method))
        return 200, self.body


def _wire_fake_real_reader(monkeypatch: pytest.MonkeyPatch, body: dict[str, Any]) -> _FakeHttp:
    fake = _FakeHttp(json.dumps(body).encode("utf-8"))
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


def test_script_uses_default_snapshot_path_when_env_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """argparse default for --snapshot-path matches the documented constant."""
    mod = _load_script()
    parser = mod._build_arg_parser()
    args = parser.parse_args([])
    assert args.snapshot_path == _DEFAULT_SNAPSHOT_PATH


def test_script_uses_env_path_when_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "alt.json"
    monkeypatch.setenv("CI_GOVERNANCE_SNAPSHOT_PATH", str(target))
    mod = _load_script()
    parser = mod._build_arg_parser()
    args = parser.parse_args([])
    assert args.snapshot_path == str(target)


def test_script_exits_2_when_in_memory_mode_and_no_token(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "snap.json"
    mod = _load_script()
    rc = mod.main(["--snapshot-path", str(target)])
    assert rc == 2
    assert not target.exists(), "no snapshot must be written in cron-safe mode"


def test_script_exits_0_on_capture_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = tmp_path / "snap.json"
    monkeypatch.setenv("CI_GOVERNANCE_GH_TOKEN", "tok-x")
    monkeypatch.setenv("CI_GOVERNANCE_READER_MODE", "gh_api")
    payload = {
        "required_status_checks": {
            "strict": True,
            "checks": [{"context": "Smoke Gate (mock tier)"}],
        },
        "enforce_admins": {"enabled": False},
    }
    fake = _wire_fake_real_reader(monkeypatch, payload)
    mod = _load_script()
    rc = mod.main(["--snapshot-path", str(target)])
    out = capsys.readouterr().out
    result = json.loads(out.strip())
    assert rc == 0
    assert result["success"] is True
    assert target.is_file()
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written == payload
    # FakeHttp confirms the real-API reader was actually used.
    assert fake.calls, "real-API reader was not invoked"
    assert fake.calls[0][2] == "GET"
