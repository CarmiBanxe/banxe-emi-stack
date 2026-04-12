"""
tests/test_doc_sync.py
IL-091 | banxe-emi-stack

Tests for scripts/doc-sync.py.
Uses importlib.util to load the hyphenated filename without sys.path manipulation.
All tests are synchronous (doc-sync.py has no async code).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

# ── Load scripts/doc-sync.py by file path ─────────────────────────────────────

_SCRIPT = Path(__file__).parent.parent / "scripts" / "doc-sync.py"
_spec = importlib.util.spec_from_file_location("doc_sync", _SCRIPT)
assert _spec is not None and _spec.loader is not None, f"Cannot load {_SCRIPT}"
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

extract_il_id: callable = _mod.extract_il_id
extract_type: callable = _mod.extract_type
classify: callable = _mod.classify
DocSync: type = _mod.DocSync
find_repo_root: callable = _mod.find_repo_root
CommitInfo: type = _mod.CommitInfo


# ── Shared fixture ─────────────────────────────────────────────────────────────

_COMMIT: dict = {
    "hash": "abc1234567890def1234567890abc1234567890ab",
    "short_hash": "abc1234",
    "message": "feat(IL-SAF-01): add safeguarding engine",
    "body": "feat(IL-SAF-01): add safeguarding engine\n\nFull engine implementation.",
    "author": "Moriel Carmi",
    "date": "2026-04-12 10:00:00 +0100",
    "changed_files": ["services/safeguarding/service.py", "tests/test_safeguarding.py"],
}


def _repos(tmp: str) -> tuple[Path, Path]:
    """Create minimal repo_root and arch_repo directories under *tmp*."""
    repo = Path(tmp) / "banxe-emi-stack"
    arch = Path(tmp) / "banxe-architecture"
    repo.mkdir()
    arch.mkdir()
    return repo, arch


# ══════════════════════════════════════════════════════════════════════════════
# extract_il_id
# ══════════════════════════════════════════════════════════════════════════════


class TestExtractIlId(unittest.TestCase):
    def test_compound_style(self) -> None:
        self.assertEqual(extract_il_id("feat(IL-SAF-01): add service"), "IL-SAF-01")

    def test_retro_compound_style(self) -> None:
        self.assertEqual(extract_il_id("docs(IL-RETRO-02): backfill"), "IL-RETRO-02")

    def test_numeric_inline(self) -> None:
        self.assertEqual(extract_il_id("chore: bump IL-090 refs"), "IL-090")

    def test_returns_none_when_absent(self) -> None:
        self.assertIsNone(extract_il_id("fix: correct decimal handling"))

    def test_extracts_first_when_multiple(self) -> None:
        self.assertEqual(
            extract_il_id("feat(IL-CKS-01): refs IL-RTM-01"),
            "IL-CKS-01",
        )

    def test_mid_sentence_extraction(self) -> None:
        self.assertEqual(
            extract_il_id("chore: update for IL-MCP-01 tools"),
            "IL-MCP-01",
        )


# ══════════════════════════════════════════════════════════════════════════════
# extract_type
# ══════════════════════════════════════════════════════════════════════════════


class TestExtractType(unittest.TestCase):
    def test_feat(self) -> None:
        self.assertEqual(extract_type("feat(scope): add feature"), "feat")

    def test_fix(self) -> None:
        self.assertEqual(extract_type("fix: correct edge case"), "fix")

    def test_refactor(self) -> None:
        self.assertEqual(extract_type("refactor(services): restructure"), "refactor")

    def test_docs(self) -> None:
        self.assertEqual(extract_type("docs: update API.md"), "docs")

    def test_returns_none_for_no_prefix(self) -> None:
        self.assertIsNone(extract_type("IL-090 retroactive entry"))

    def test_returns_none_for_uppercase(self) -> None:
        # Conventional commits require lowercase type
        self.assertIsNone(extract_type("Feat: add something"))


# ══════════════════════════════════════════════════════════════════════════════
# classify
# ══════════════════════════════════════════════════════════════════════════════


class TestClassify(unittest.TestCase):
    def test_commit_log_always_present(self) -> None:
        needs = classify(None, [], "chore: bump deps")
        self.assertIn("commit-log.jsonl", needs)

    def test_feat_adds_ledger_and_memory(self) -> None:
        needs = classify("feat", [], "feat: add feature")
        self.assertIn("INSTRUCTION-LEDGER", needs)
        self.assertIn("MEMORY.md", needs)

    def test_refactor_adds_ledger_and_memory(self) -> None:
        needs = classify("refactor", [], "refactor: split module")
        self.assertIn("INSTRUCTION-LEDGER", needs)
        self.assertIn("MEMORY.md", needs)

    def test_fix_does_not_add_ledger(self) -> None:
        needs = classify("fix", [], "fix: null pointer")
        self.assertNotIn("INSTRUCTION-LEDGER", needs)

    def test_services_file_triggers_services_map(self) -> None:
        needs = classify(None, ["services/recon/engine.py"], "chore: update")
        self.assertIn(".claude/memory/services-map.md", needs)

    def test_api_file_triggers_api_changelog(self) -> None:
        needs = classify(None, ["api/v1/routers.py"], "feat: new endpoint")
        self.assertIn("docs/API-CHANGELOG.md", needs)

    def test_tests_file_triggers_coverage(self) -> None:
        needs = classify(None, ["tests/test_recon.py"], "test: add coverage")
        self.assertIn(".claude/memory/test-coverage.md", needs)

    def test_docker_file_triggers_infra_state(self) -> None:
        needs = classify(None, ["docker/docker-compose.yml"], "chore: update docker")
        self.assertIn(".claude/memory/infra-state.md", needs)

    def test_frontend_file_triggers_frontend_state(self) -> None:
        needs = classify(None, ["frontend/src/App.tsx"], "feat: dashboard")
        self.assertIn(".claude/memory/frontend-state.md", needs)

    def test_architectural_keyword_triggers_adr(self) -> None:
        needs = classify("feat", [], "feat: new service for payments")
        self.assertIn("ADR", needs)

    def test_switched_from_triggers_adr(self) -> None:
        needs = classify("feat", [], "feat: switched from flask to fastapi")
        self.assertIn("ADR", needs)

    def test_rules_file_triggers_quality_gates_state(self) -> None:
        needs = classify(None, [".claude/rules/quality-gates.md"], "docs: update rules")
        self.assertIn(".claude/memory/quality-gates-state.md", needs)

    def test_playbooks_file_triggers_playbooks_registry(self) -> None:
        needs = classify(None, ["config/playbooks/onboarding.yml"], "chore: update")
        self.assertIn(".claude/memory/playbooks-registry.md", needs)

    def test_no_duplicates_in_output(self) -> None:
        needs = classify(
            "feat",
            ["services/foo.py", "api/routes.py"],
            "feat: new service migration",
        )
        self.assertEqual(len(needs), len(set(needs)))


# ══════════════════════════════════════════════════════════════════════════════
# DocSync — dry-run
# ══════════════════════════════════════════════════════════════════════════════


class TestDryRun(unittest.TestCase):
    def test_no_files_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, arch = _repos(tmp)
            syncer = DocSync(_COMMIT, dry_run=True, repo_root=repo, arch_repo=arch)
            syncer.run()
            # The memory directory must NOT be created at all
            self.assertFalse((repo / ".claude" / "memory").exists())

    def test_report_still_populated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, arch = _repos(tmp)
            syncer = DocSync(_COMMIT, dry_run=True, repo_root=repo, arch_repo=arch)
            syncer.run()
            self.assertGreater(len(syncer.report), 0)

    def test_test_coverage_skipped_in_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, arch = _repos(tmp)
            commit = {**_COMMIT, "changed_files": ["tests/test_foo.py"]}
            syncer = DocSync(commit, dry_run=True, repo_root=repo, arch_repo=arch)
            syncer.run()
            statuses = [s for _, s in syncer.report]
            self.assertTrue(any("skipped" in s for s in statuses))


# ══════════════════════════════════════════════════════════════════════════════
# DocSync — commit-log.jsonl
# ══════════════════════════════════════════════════════════════════════════════


class TestCommitLog(unittest.TestCase):
    def test_creates_valid_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, arch = _repos(tmp)
            syncer = DocSync(_COMMIT, dry_run=False, repo_root=repo, arch_repo=arch)
            syncer._update_commit_log()

            log = repo / ".claude" / "memory" / "commit-log.jsonl"
            self.assertTrue(log.exists())
            data = json.loads(log.read_text(encoding="utf-8").strip())
            self.assertEqual(data["hash"], "abc1234")
            self.assertEqual(data["il_id"], "IL-SAF-01")
            self.assertEqual(data["type"], "feat")
            self.assertIsInstance(data["changed_files"], list)

    def test_appends_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, arch = _repos(tmp)
            syncer = DocSync(_COMMIT, dry_run=False, repo_root=repo, arch_repo=arch)
            syncer._update_commit_log()
            syncer._update_commit_log()

            log = repo / ".claude" / "memory" / "commit-log.jsonl"
            lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
            self.assertEqual(len(lines), 2)
            for line in lines:
                json.loads(line)  # each line must be valid JSON

    def test_full_hash_stored_in_full_hash_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, arch = _repos(tmp)
            syncer = DocSync(_COMMIT, dry_run=False, repo_root=repo, arch_repo=arch)
            syncer._update_commit_log()

            log = repo / ".claude" / "memory" / "commit-log.jsonl"
            data = json.loads(log.read_text(encoding="utf-8").strip())
            self.assertEqual(data["full_hash"], _COMMIT["hash"])
            self.assertNotEqual(data["hash"], data["full_hash"])

    def test_report_entry_added(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, arch = _repos(tmp)
            syncer = DocSync(_COMMIT, dry_run=False, repo_root=repo, arch_repo=arch)
            syncer._update_commit_log()
            docs = [d for d, _ in syncer.report]
            self.assertIn("commit-log.jsonl", docs)


# ══════════════════════════════════════════════════════════════════════════════
# DocSync — INSTRUCTION-LEDGER
# ══════════════════════════════════════════════════════════════════════════════


class TestInstructionLedger(unittest.TestCase):
    def test_appends_new_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, arch = _repos(tmp)
            ledger = arch / "INSTRUCTION-LEDGER.md"
            ledger.write_text("# INSTRUCTION-LEDGER\n\n", encoding="utf-8")

            syncer = DocSync(_COMMIT, dry_run=False, repo_root=repo, arch_repo=arch)
            syncer._update_instruction_ledger("IL-SAF-01")

            content = ledger.read_text(encoding="utf-8")
            self.assertIn("IL-SAF-01", content)
            self.assertIn("DONE ✅", content)
            self.assertIn("abc1234", content)

    def test_skips_existing_il_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, arch = _repos(tmp)
            ledger = arch / "INSTRUCTION-LEDGER.md"
            ledger.write_text("# LEDGER\n\n### IL-SAF-01 — existing\n", encoding="utf-8")
            original_size = ledger.stat().st_size

            syncer = DocSync(_COMMIT, dry_run=False, repo_root=repo, arch_repo=arch)
            syncer._update_instruction_ledger("IL-SAF-01")

            # File should not grow
            self.assertEqual(ledger.stat().st_size, original_size)
            statuses = [s for _, s in syncer.report]
            self.assertTrue(any("already present" in s for s in statuses))

    def test_reports_file_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, arch = _repos(tmp)
            # Do NOT create INSTRUCTION-LEDGER.md
            syncer = DocSync(_COMMIT, dry_run=False, repo_root=repo, arch_repo=arch)
            syncer._update_instruction_ledger("IL-SAF-01")

            statuses = [s for _, s in syncer.report]
            self.assertTrue(any("not found" in s for s in statuses))

    def test_strips_type_scope_from_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, arch = _repos(tmp)
            ledger = arch / "INSTRUCTION-LEDGER.md"
            ledger.write_text("# LEDGER\n\n", encoding="utf-8")

            syncer = DocSync(_COMMIT, dry_run=False, repo_root=repo, arch_repo=arch)
            syncer._update_instruction_ledger("IL-SAF-01")

            content = ledger.read_text(encoding="utf-8")
            # Title should be clean text, not "feat(IL-SAF-01): add safeguarding engine"
            self.assertNotIn("feat(", content.split("IL-SAF-01 —")[1].split("\n")[0])


# ══════════════════════════════════════════════════════════════════════════════
# DocSync — services-map.md
# ══════════════════════════════════════════════════════════════════════════════


class TestServicesMap(unittest.TestCase):
    def test_lists_services_with_init(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, arch = _repos(tmp)
            # Create fake services with __init__.py
            for svc in ("recon", "reporting", "aml"):
                (repo / "services" / svc).mkdir(parents=True)
                (repo / "services" / svc / "__init__.py").write_text("", encoding="utf-8")

            syncer = DocSync(_COMMIT, dry_run=False, repo_root=repo, arch_repo=arch)
            syncer._update_services_map()

            smap = (repo / ".claude" / "memory" / "services-map.md").read_text(encoding="utf-8")
            self.assertIn("services/aml/", smap)
            self.assertIn("services/recon/", smap)
            self.assertIn("services/reporting/", smap)

    def test_handles_missing_services_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, arch = _repos(tmp)
            syncer = DocSync(_COMMIT, dry_run=False, repo_root=repo, arch_repo=arch)
            syncer._update_services_map()

            statuses = [s for _, s in syncer.report]
            self.assertTrue(any("not found" in s for s in statuses))


# ══════════════════════════════════════════════════════════════════════════════
# find_repo_root
# ══════════════════════════════════════════════════════════════════════════════


class TestFindRepoRoot(unittest.TestCase):
    def test_finds_root_from_nested_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "myproject"
            (repo / ".git").mkdir(parents=True)
            subdir = repo / "a" / "b" / "c"
            subdir.mkdir(parents=True)

            result = find_repo_root(subdir)
            self.assertEqual(result, repo)

    def test_finds_root_from_direct_child(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "myproject"
            (repo / ".git").mkdir(parents=True)
            child = repo / "scripts"
            child.mkdir()

            result = find_repo_root(child)
            self.assertEqual(result, repo)

    def test_raises_when_no_git_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp) / "not-a-repo"
            plain.mkdir()
            with self.assertRaises(RuntimeError):
                find_repo_root(plain)


# ══════════════════════════════════════════════════════════════════════════════
# DocSync — full run integration
# ══════════════════════════════════════════════════════════════════════════════


class TestFullRun(unittest.TestCase):
    def test_run_produces_report_for_all_needs(self) -> None:
        """run() must emit a report entry for every doc key in classify()."""
        with tempfile.TemporaryDirectory() as tmp:
            repo, arch = _repos(tmp)
            commit = {
                **_COMMIT,
                "message": "feat(IL-TEST-01): add new service migration",
                "changed_files": [
                    "services/foo/bar.py",
                    "api/v1/routes.py",
                    "docker/docker-compose.yml",
                    "frontend/src/App.tsx",
                    "tests/test_foo.py",
                ],
            }
            syncer = DocSync(commit, dry_run=True, repo_root=repo, arch_repo=arch)
            syncer.run()

            reported_docs = {d for d, _ in syncer.report}
            expected = {
                "commit-log.jsonl",
                "INSTRUCTION-LEDGER",
                "MEMORY.md",
                ".claude/memory/services-map.md",
                "docs/API-CHANGELOG.md",
                ".claude/memory/infra-state.md",
                ".claude/memory/frontend-state.md",
                ".claude/memory/test-coverage.md",
                "ADR",
            }
            self.assertTrue(expected.issubset(reported_docs))

    def test_run_with_no_il_id_warns_for_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo, arch = _repos(tmp)
            commit = {**_COMMIT, "message": "feat: add feature with no IL id"}
            syncer = DocSync(commit, dry_run=True, repo_root=repo, arch_repo=arch)
            syncer.run()

            statuses = {s for _, s in syncer.report}
            self.assertTrue(any("no IL-ID" in s for s in statuses))


if __name__ == "__main__":
    unittest.main(verbosity=2)
