#!/usr/bin/env python3
"""doc-sync.py — Auto-sync documentation after a git commit.

Usage:
    python scripts/doc-sync.py [--commit HASH] [--dry-run] [--auto-push]

Stdlib only — no pip install required.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import TypedDict

# ── Commit data structure ──────────────────────────────────────────────────────


class CommitInfo(TypedDict):
    hash: str
    short_hash: str
    message: str
    body: str
    author: str
    date: str
    changed_files: list[str]


# ── Repo discovery ─────────────────────────────────────────────────────────────


def find_repo_root(start: Path) -> Path:
    """Walk up from *start* until a .git directory is found."""
    current = start.resolve()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    raise RuntimeError(f"No git repository found starting from {start}")


# ── Git helpers ────────────────────────────────────────────────────────────────


def _run_git(args: list[str], cwd: Path) -> str:
    """Run a git command in *cwd* and return stripped stdout."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def parse_commit(commit_hash: str, cwd: Path) -> CommitInfo:
    """Resolve *commit_hash* and return its metadata."""
    full = _run_git(["rev-parse", commit_hash], cwd)
    raw_files = _run_git(["diff-tree", "--no-commit-id", "-r", "--name-only", full], cwd)
    return CommitInfo(
        hash=full,
        short_hash=full[:7],
        message=_run_git(["log", "-1", "--format=%s", full], cwd),
        body=_run_git(["log", "-1", "--format=%B", full], cwd),
        author=_run_git(["log", "-1", "--format=%an", full], cwd),
        date=_run_git(["log", "-1", "--format=%ai", full], cwd),
        changed_files=[f for f in raw_files.splitlines() if f],
    )


# ── Extractors ─────────────────────────────────────────────────────────────────


def extract_il_id(message: str) -> str | None:
    """Return the first IL identifier found in *message*, or None.

    Matches compound (IL-SAF-01, IL-RETRO-02) and numeric (IL-090) forms.
    """
    m = re.search(r"IL-(?:[A-Z]+-\d+|\d+)", message)
    return m.group(0) if m else None


def extract_type(message: str) -> str | None:
    """Return the conventional-commit type prefix from *message*, or None."""
    m = re.match(
        r"^(feat|fix|docs|refactor|test|chore|scaffold|perf|ci|style|build)\b",
        message,
    )
    return m.group(1) if m else None


# ── Classification ─────────────────────────────────────────────────────────────

_ARCH_KEYWORDS: list[str] = [
    "new service",
    "new protocol",
    "migration",
    "new database",
    "new framework",
    "replaced",
    "switched from",
]


def classify(
    commit_type: str | None,
    changed_files: list[str],
    message: str,
) -> list[str]:
    """Return the ordered list of document keys that need updating."""
    needs: list[str] = ["commit-log.jsonl"]  # always

    if commit_type in ("feat", "refactor"):
        needs.append("INSTRUCTION-LEDGER")
        needs.append("MEMORY.md")

    if any("services/" in f for f in changed_files):
        needs.append(".claude/memory/services-map.md")
    if any("api/" in f for f in changed_files):
        needs.append("docs/API-CHANGELOG.md")
    if any(".claude/rules/" in f for f in changed_files):
        needs.append(".claude/memory/quality-gates-state.md")
    if any("config/playbooks/" in f for f in changed_files):
        needs.append(".claude/memory/playbooks-registry.md")
    if any("docker/" in f for f in changed_files):
        needs.append(".claude/memory/infra-state.md")
    if any("frontend/" in f for f in changed_files):
        needs.append(".claude/memory/frontend-state.md")
    if any(f.startswith("tests/") for f in changed_files):
        needs.append(".claude/memory/test-coverage.md")

    if any(kw in message.lower() for kw in _ARCH_KEYWORDS):
        needs.append("ADR")

    return needs


# ── DocSync ────────────────────────────────────────────────────────────────────


class DocSync:
    """Orchestrate all documentation updates for a single commit."""

    def __init__(
        self,
        commit: CommitInfo,
        dry_run: bool,
        repo_root: Path,
        arch_repo: Path,
    ) -> None:
        self.commit = commit
        self.dry_run = dry_run
        self.repo_root = repo_root
        self.arch_repo = arch_repo
        self.report: list[tuple[str, str]] = []

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _append_file(self, path: Path, text: str) -> None:
        """Append *text* to *path*, creating parent dirs as needed. No-op in dry-run."""
        if self.dry_run:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)

    @property
    def _hash(self) -> str:
        return self.commit["short_hash"]

    @property
    def _msg(self) -> str:
        return self.commit["message"]

    @property
    def _date(self) -> str:
        return self.commit["date"].split()[0]

    # ── Individual updaters ────────────────────────────────────────────────────

    def _update_commit_log(self) -> None:
        path = self.repo_root / ".claude" / "memory" / "commit-log.jsonl"
        entry: dict[str, object] = {
            "hash": self._hash,
            "full_hash": self.commit["hash"],
            "message": self._msg,
            "author": self.commit["author"],
            "date": self.commit["date"],
            "il_id": extract_il_id(self._msg),
            "type": extract_type(self._msg),
            "changed_files": self.commit["changed_files"],
        }
        self._append_file(path, json.dumps(entry, ensure_ascii=False) + "\n")
        self.report.append(("commit-log.jsonl", "✅ updated"))

    def _update_instruction_ledger(self, il_id: str) -> None:
        path = self.arch_repo / "INSTRUCTION-LEDGER.md"
        if not path.exists():
            self.report.append(("INSTRUCTION-LEDGER", "❌ file not found"))
            return
        content = path.read_text(encoding="utf-8")
        if il_id in content:
            self.report.append(("INSTRUCTION-LEDGER", f"⚠️  {il_id} already present"))
            return
        title = re.sub(r"^[a-z]+\([^)]+\):\s*", "", self._msg).strip()
        block = (
            f"\n### {il_id} — {title}\n"
            f"- **Источник:** auto-sync | **Приоритет:** P1 | **Репо:** banxe-emi-stack\n"
            f"- **Описание:** {self._msg}\n"
            f"- **Статус:** DONE ✅ {self._date}\n"
            f"- **Proof:** commit {self._hash} banxe-emi-stack\n"
        )
        self._append_file(path, block)
        self.report.append(("INSTRUCTION-LEDGER", f"✅ appended {il_id}"))

    def _update_memory_md(self) -> None:
        path = self.arch_repo / "MEMORY.md"
        if not path.exists():
            self.report.append(("MEMORY.md", "⚠️  not found — needs manual review"))
            return
        self._append_file(path, f"- [{self._date}] {self._hash} — {self._msg}\n")
        self.report.append(("MEMORY.md", "⚠️  needs manual review"))

    def _update_services_map(self) -> None:
        path = self.repo_root / ".claude" / "memory" / "services-map.md"
        svc_dir = self.repo_root / "services"
        if not svc_dir.exists():
            self.report.append((".claude/memory/services-map.md", "⚠️  services/ not found"))
            return
        names = sorted(
            p.parent.name for p in svc_dir.rglob("__init__.py") if p.parent.parent == svc_dir
        )
        lines = [f"\n## Updated {self._date} [{self._hash}]\n"]
        lines.extend(f"- `services/{n}/`\n" for n in names)
        self._append_file(path, "".join(lines))
        self.report.append((".claude/memory/services-map.md", "✅ updated"))

    def _update_test_coverage(self) -> None:
        path = self.repo_root / ".claude" / "memory" / "test-coverage.md"
        if self.dry_run:
            self.report.append((".claude/memory/test-coverage.md", "⏭️  skipped (dry run)"))
            return
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "--co", "-q", "--override-ini=addopts="],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=120,
            )
            combined = proc.stdout + proc.stderr
            m = re.search(r"(\d+) tests? collected", combined)
            count = m.group(0) if m else "count unknown"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            count = "pytest unavailable"
        self._append_file(path, f"- {self._date} [{self._hash}] {count}\n")
        self.report.append((".claude/memory/test-coverage.md", f"✅ {count}"))

    def _append_generic(self, doc_key: str) -> None:
        """Append a timestamped line to any unspecialised .claude/memory/* path."""
        path = self.repo_root / doc_key.lstrip("/")
        self._append_file(path, f"- {self._date} [{self._hash}] {self._msg}\n")
        self.report.append((doc_key, "✅ updated"))

    # ── Orchestration ──────────────────────────────────────────────────────────

    def run(self) -> None:
        """Process all documents required for this commit."""
        il_id = extract_il_id(self._msg)
        commit_type = extract_type(self._msg)
        needs = classify(commit_type, self.commit["changed_files"], self._msg)

        for doc in needs:
            if doc == "commit-log.jsonl":
                self._update_commit_log()
            elif doc == "INSTRUCTION-LEDGER":
                if il_id:
                    self._update_instruction_ledger(il_id)
                else:
                    self.report.append(("INSTRUCTION-LEDGER", "⚠️  no IL-ID in commit message"))
            elif doc == "MEMORY.md":
                self._update_memory_md()
            elif doc == ".claude/memory/services-map.md":
                self._update_services_map()
            elif doc == ".claude/memory/test-coverage.md":
                self._update_test_coverage()
            elif doc == "ADR":
                self.report.append(("ADR", "❌ requires manual creation"))
            else:
                self._append_generic(doc)

    def print_report(self) -> None:
        """Print a formatted two-column summary table to stdout."""
        col = 46
        bar = "─" * (col + 22)
        tag = "  [DRY RUN]" if self.dry_run else ""
        print(f"\n{bar}")
        print(f"  doc-sync  commit={self._hash}{tag}")
        print(bar)
        print(f"  {'Document':<{col}} Status")
        print(f"  {'─' * (col - 2)} {'─' * 18}")
        for doc, status in self.report:
            print(f"  {doc:<{col}} {status}")
        print(f"{bar}\n")


# ── Auto-push ──────────────────────────────────────────────────────────────────


def _push_repo(repo: Path, add_args: list[str], msg: str) -> None:
    """Stage, commit, and push changes in *repo*. Handles nothing-to-commit gracefully."""
    if not repo.exists():
        print(f"  ⚠️  repo not found: {repo}")
        return
    try:
        _run_git(["add", *add_args], repo)
        _run_git(["commit", "-m", msg], repo)
        _run_git(["push"], repo)
        print(f"  ✅ pushed {repo.name}")
    except RuntimeError as exc:
        err = str(exc)
        if "nothing to commit" in err:
            print(f"  ℹ️  {repo.name}: nothing to commit")
        else:
            print(f"  ❌ {repo.name}: {err.splitlines()[0]}")


def auto_push(repo_root: Path, arch_repo: Path, short_hash: str) -> None:
    """Commit and push documentation changes in both repos."""
    msg = f"docs: auto-sync after {short_hash}"
    print("\nAuto-push:")
    _push_repo(repo_root, [".claude/memory/", "docs/"], msg)
    _push_repo(arch_repo, ["-A"], msg)


# ── CLI ────────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Sync documentation after a git commit (stdlib only).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--commit",
        default="HEAD",
        metavar="HASH",
        help="commit to process (default: HEAD)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be done without writing any files",
    )
    p.add_argument(
        "--auto-push",
        action="store_true",
        help="commit and push doc changes in both repos after syncing",
    )
    return p


def main() -> int:
    args = _build_parser().parse_args()

    try:
        repo_root = find_repo_root(Path(__file__).parent)
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    arch_repo = repo_root.parent / "banxe-architecture"

    try:
        commit = parse_commit(args.commit, repo_root)
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        il_id = extract_il_id(commit["message"])
        commit_type = extract_type(commit["message"])
        needs = classify(commit_type, commit["changed_files"], commit["message"])
        print(f"\n[DRY RUN] commit={commit['short_hash']}  type={commit_type}  il_id={il_id}")
        print(f"Would update: {', '.join(needs)}\n")

    syncer = DocSync(commit, args.dry_run, repo_root, arch_repo)
    syncer.run()
    syncer.print_report()

    if args.auto_push and not args.dry_run:
        auto_push(repo_root, arch_repo, commit["short_hash"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
