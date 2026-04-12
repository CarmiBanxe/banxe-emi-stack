"""
services/experiment_copilot/agents/change_proposer.py — Change Proposer
IL-CEC-01 | banxe-emi-stack

Converts approved experiments to Git PRs and GitHub issues.
Uses subprocess + git CLI and GitHub REST API (via httpx).
All GitHub API calls are mocked in tests.
"""

from __future__ import annotations

import logging
from pathlib import Path
import subprocess
from typing import Any, Protocol, runtime_checkable

from services.experiment_copilot.models.experiment import ComplianceExperiment
from services.experiment_copilot.models.proposal import (
    ChangeProposal,
    HITLChecklist,
    ProposalStatus,
    ProposeRequest,
)
from services.experiment_copilot.store.audit_trail import AuditTrail

logger = logging.getLogger("banxe.experiment_copilot.proposer")


# ── GitHub Port (Protocol DI) ──────────────────────────────────────────────


@runtime_checkable
class GitHubPort(Protocol):
    def create_pr(
        self, branch: str, title: str, body: str, base: str = "main"
    ) -> dict[str, Any]: ...

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict[str, Any]: ...


class InMemoryGitHubPort:
    """Test stub — records PR/issue creation calls."""

    def __init__(self) -> None:
        self.prs_created: list[dict[str, Any]] = []
        self.issues_created: list[dict[str, Any]] = []
        self._pr_counter = 1
        self._issue_counter = 1

    def create_pr(self, branch: str, title: str, body: str, base: str = "main") -> dict[str, Any]:
        pr = {
            "number": self._pr_counter,
            "html_url": f"https://github.com/CarmiBanxe/banxe-emi-stack/pull/{self._pr_counter}",
            "title": title,
            "branch": branch,
        }
        self.prs_created.append(pr)
        self._pr_counter += 1
        return pr

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict[str, Any]:
        issue = {
            "number": self._issue_counter,
            "html_url": f"https://github.com/CarmiBanxe/banxe-emi-stack/issues/{self._issue_counter}",
            "title": title,
        }
        self.issues_created.append(issue)
        self._issue_counter += 1
        return issue


class HTTPGitHubPort:
    """Production GitHub REST API port."""

    def __init__(self, token: str, repo: str) -> None:
        self._token = token
        self._repo = repo

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def create_pr(self, branch: str, title: str, body: str, base: str = "main") -> dict[str, Any]:
        import httpx

        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                f"https://api.github.com/repos/{self._repo}/pulls",
                headers=self._headers(),
                json={"title": title, "body": body, "head": branch, "base": base},
            )
            r.raise_for_status()
            return r.json()

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict[str, Any]:
        import httpx

        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                f"https://api.github.com/repos/{self._repo}/issues",
                headers=self._headers(),
                json={"title": title, "body": body, "labels": labels},
            )
            r.raise_for_status()
            return r.json()


# ── Change Proposer ────────────────────────────────────────────────────────


class ChangeProposer:
    """Creates Git branches, updates config files, and opens GitHub PRs/issues.

    HITL invariant: every PR includes a human approval checklist.
    dry_run=True (default) generates the PR body without creating branch/PR.
    """

    def __init__(
        self,
        audit: AuditTrail,
        github: GitHubPort | None = None,
        template_path: str = "config/templates/compliance_pr_template.md",
        repo_root: str = ".",
    ) -> None:
        self._audit = audit
        self._github = github or InMemoryGitHubPort()
        self._template_path = Path(template_path)
        self._repo_root = Path(repo_root)

    def propose(self, experiment: ComplianceExperiment, request: ProposeRequest) -> ChangeProposal:
        """Convert an approved experiment into a Git PR + GitHub issue.

        Args:
            experiment: The approved ComplianceExperiment to propose.
            request: ProposeRequest with dry_run flag.

        Returns:
            ChangeProposal with PR URL and HITL checklist.

        Raises:
            ValueError: If experiment is not in ACTIVE status.
        """
        from services.experiment_copilot.models.experiment import ExperimentStatus

        if experiment.status != ExperimentStatus.ACTIVE:
            raise ValueError(
                f"Only ACTIVE experiments can be proposed. Got: {experiment.status.value}"
            )

        branch_name = f"compliance/exp-{experiment.id}"
        pr_title = f"[Compliance Experiment] {experiment.title}"
        pr_body = self._render_pr_body(experiment)

        proposal = ChangeProposal(
            experiment_id=experiment.id,
            branch_name=branch_name,
            pr_title=pr_title,
            pr_body=pr_body,
            hitl_checklist=HITLChecklist(),
            files_changed=self._predict_files_changed(experiment),
        )

        if request.dry_run:
            proposal.status = ProposalStatus.PENDING
            logger.info("[DRY RUN] Proposal for %s — no branch created", experiment.id)
            self._audit.log(
                actor="claude-code",
                action="experiment.proposal.dry_run",
                experiment_id=experiment.id,
                details={"branch": branch_name, "dry_run": True},
            )
            return proposal

        # Live mode: create branch, PR, issue
        try:
            self._create_branch(branch_name)
            pr = self._github.create_pr(branch=branch_name, title=pr_title, body=pr_body)
            issue = self._github.create_issue(
                title=f"Track: {pr_title}",
                body=pr_body,
                labels=["compliance", "experiment", experiment.scope.value],
            )
            proposal.pr_url = pr.get("html_url")
            proposal.issue_url = issue.get("html_url")
            proposal.status = ProposalStatus.PENDING

            self._audit.log(
                actor="claude-code",
                action="experiment.proposal.created",
                experiment_id=experiment.id,
                details={
                    "branch": branch_name,
                    "pr_url": proposal.pr_url,
                    "issue_url": proposal.issue_url,
                },
            )
            logger.info("Created PR %s for experiment %s", proposal.pr_url, experiment.id)

        except Exception as exc:
            logger.error("Failed to create proposal for %s: %s", experiment.id, exc)
            proposal.status = ProposalStatus.REJECTED
            raise

        return proposal

    # ── Internal ───────────────────────────────────────────────────────────

    def _render_pr_body(self, exp: ComplianceExperiment) -> str:
        """Render the compliance PR body using the template."""
        template = self._load_template()

        citations_table = self._format_citations_table(exp.kb_citations)
        metrics_table = self._format_metrics_table(exp.metrics_baseline, exp.metrics_target)
        hitl_checklist = "\n".join(
            [
                "- [ ] CTIO reviewed and approved",
                "- [ ] Compliance officer sign-off",
                "- [ ] Backtest results reviewed",
                "- [ ] Rollback plan defined",
            ]
        )

        return template.format(
            title=exp.title,
            scope=exp.scope.value,
            created_at=exp.created_at.strftime("%Y-%m-%d"),
            created_by=exp.created_by,
            hypothesis=exp.hypothesis,
            kb_citations_table=citations_table,
            metrics_table=metrics_table,
            hitl_checklist=hitl_checklist,
            experiment_id=exp.id,
        )

    def _load_template(self) -> str:
        if self._template_path.exists():
            return self._template_path.read_text(encoding="utf-8")
        return _DEFAULT_PR_TEMPLATE

    @staticmethod
    def _format_citations_table(citation_ids: list[str]) -> str:
        if not citation_ids:
            return "_No citations — steward must add before approval_"
        rows = [f"| {cid} |" for cid in citation_ids]
        return "| Source ID |\n|----------|\n" + "\n".join(rows)

    @staticmethod
    def _format_metrics_table(baseline: dict, target: dict) -> str:
        metrics = ["hit_rate_24h", "false_positive_rate", "sar_yield"]
        rows = []
        for m in metrics:
            b = baseline.get(m, "N/A")
            t = target.get(m, "N/A")
            rows.append(f"| {m} | {b} | {t} |")
        header = "| Metric | Baseline | Target |\n|--------|----------|--------|"
        return header + "\n" + "\n".join(rows)

    def _predict_files_changed(self, exp: ComplianceExperiment) -> list[str]:
        return [
            f"compliance-experiments/active/{exp.id}.yaml",
            "config/aml_rules.yaml",
        ]

    def _create_branch(self, branch_name: str) -> None:
        """Create and checkout a new git branch."""
        try:
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=self._repo_root,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Failed to create branch '{branch_name}': {exc.stderr}") from exc


# ── Default PR template (fallback if file missing) ────────────────────────

_DEFAULT_PR_TEMPLATE = """\
## Compliance Experiment: {title}

**Scope**: `{scope}` | **Created**: {created_at} | **Author**: {created_by}
**Experiment ID**: `{experiment_id}`

### Hypothesis
{hypothesis}

### Knowledge Base Citations
{kb_citations_table}

### Metrics
{metrics_table}

### Human-in-the-Loop Checklist
{hitl_checklist}

---
_Generated by Banxe Compliance Experiment Copilot (IL-CEC-01)_
"""
