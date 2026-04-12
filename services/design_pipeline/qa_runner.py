"""
services/design_pipeline/qa_runner.py — CI/CD QA Runner
IL-D2C-01 | BANXE EMI AI Bank

Coordinates visual regression testing:
  - BackstopJS config generation for Storybook integration
  - Loki integration for Storybook snapshot testing
  - GitHub Actions CI hook generation
  - Batch component QA runs
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from typing import Any

from services.design_pipeline.models import QAStatus, VisualQAResult
from services.design_pipeline.visual_qa import BackstopConfigGenerator, InMemoryVisualQA

logger = logging.getLogger("banxe.design_pipeline.qa_runner")


@dataclass
class QARunSummary:
    """Summary of a batch QA run."""

    total: int
    passed: int
    failed: int
    skipped: int
    results: list[VisualQAResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.passed / self.total

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and self.total > 0


class DesignQARunner:
    """
    Coordinates batch visual QA runs for CI/CD pipelines.

    Generates BackstopJS configs, runs batch comparisons,
    and writes CI-compatible output.
    """

    def __init__(
        self,
        visual_qa: Any | None = None,
        storybook_url: str = "http://localhost:6006",
        output_dir: Path | str = "tmp/qa-reports",
    ) -> None:
        self._qa = visual_qa or InMemoryVisualQA()
        self._storybook_url = storybook_url
        self._output_dir = Path(output_dir)
        self._backstop = BackstopConfigGenerator(storybook_url=storybook_url)

    async def run_batch(
        self,
        components: list[dict[str, str]],
        threshold: float = 0.95,
    ) -> QARunSummary:
        """
        Run visual QA for a batch of components.

        Args:
            components: List of dicts with keys: component_id, rendered_html, reference_svg
            threshold:  Similarity threshold (default: 0.95)

        Returns:
            QARunSummary with pass/fail counts and individual results.
        """
        results: list[VisualQAResult] = []
        for comp in components:
            result = await self._qa.compare(
                component_id=comp.get("component_id", "unknown"),
                rendered_html=comp.get("rendered_html", ""),
                reference_svg=comp.get("reference_svg", ""),
                threshold=threshold,
            )
            results.append(result)
            log_fn = logger.info if result.passed else logger.warning
            log_fn(
                "QA %s — %s (similarity=%.3f)",
                "PASS" if result.passed else "FAIL",
                result.component_id,
                result.similarity_score,
            )

        passed = sum(1 for r in results if r.status == QAStatus.PASS)
        failed = sum(1 for r in results if r.status == QAStatus.FAIL)
        skipped = sum(1 for r in results if r.status == QAStatus.SKIPPED)

        summary = QARunSummary(
            total=len(results),
            passed=passed,
            failed=failed,
            skipped=skipped,
            results=results,
        )
        logger.info(
            "QA run complete: %d/%d passed (%.1f%%)",
            passed,
            len(results),
            summary.pass_rate * 100,
        )
        return summary

    def write_backstop_config(
        self, component_names: list[str], output_path: str | None = None
    ) -> str:
        """Generate and write BackstopJS config. Returns the output path."""
        out = output_path or str(self._output_dir / "backstop.json")
        self._backstop.write_config(component_names, out)
        return out

    def write_ci_report(self, summary: QARunSummary) -> str:
        """Write a JSON CI report and return its path."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        report_path = self._output_dir / "qa-report.json"
        report: dict[str, Any] = {
            "total": summary.total,
            "passed": summary.passed,
            "failed": summary.failed,
            "skipped": summary.skipped,
            "pass_rate": round(summary.pass_rate, 4),
            "all_passed": summary.all_passed,
            "results": [
                {
                    "component_id": r.component_id,
                    "status": r.status.value,
                    "similarity_score": round(r.similarity_score, 4),
                    "diff_pixel_count": r.diff_pixel_count,
                    "diff_image_path": r.diff_image_path,
                }
                for r in summary.results
            ],
        }
        with report_path.open("w") as f:
            json.dump(report, f, indent=2)
        logger.info("CI report written to %s", report_path)
        return str(report_path)

    @staticmethod
    def generate_github_actions_workflow() -> str:
        """Generate a GitHub Actions workflow YAML for visual regression CI."""
        return """\
name: Visual Regression Tests

on:
  pull_request:
    paths:
      - "services/design_pipeline/**"
      - "config/design-tokens/**"

jobs:
  visual-regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install Playwright
        run: pip install playwright && playwright install chromium --with-deps

      - name: Run Visual QA
        env:
          PENPOT_BASE_URL: ${{ secrets.PENPOT_BASE_URL }}
          PENPOT_TOKEN: ${{ secrets.PENPOT_TOKEN }}
          VISUAL_QA_ENABLED: "true"
        run: python -m pytest tests/test_design_pipeline/test_visual_qa.py -v

      - name: Upload diff images
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: visual-qa-diffs
          path: tmp/visual-qa-diffs/
"""

    @staticmethod
    def generate_loki_config() -> dict[str, Any]:
        """Generate Loki config for Storybook snapshot testing."""
        return {
            "configurations": {
                "ci": {
                    "target": "chrome.docker",
                    "referenceDir": "./loki-reference",
                    "chromeDockerImage": "browserless/chrome:1-puppeteer-20",
                    "matchingThreshold": 0.05,
                }
            },
            "fetchFailIgnore": False,
        }
