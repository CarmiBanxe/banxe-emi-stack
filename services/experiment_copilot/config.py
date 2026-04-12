"""
services/experiment_copilot/config.py — Runtime configuration
IL-CEC-01 | banxe-emi-stack
"""

from __future__ import annotations

import os


class ExperimentConfig:
    def __init__(self) -> None:
        self.experiments_dir: str = os.environ.get("EXPERIMENTS_DIR", "compliance-experiments")
        self.baselines_path: str = os.environ.get("AML_BASELINES_PATH", "config/aml_baselines.yaml")
        self.pr_template_path: str = os.environ.get(
            "PR_TEMPLATE_PATH", "config/templates/compliance_pr_template.md"
        )
        self.audit_log_path: str = os.environ.get("AUDIT_LOG_PATH", "data/audit/experiments.jsonl")
        self.github_token: str = os.environ.get("GITHUB_TOKEN", "")
        self.github_repo: str = os.environ.get("GITHUB_REPO", "CarmiBanxe/banxe-emi-stack")
        self.clickhouse_host: str = os.environ.get("CLICKHOUSE_HOST", "localhost")
        self.clickhouse_port: int = int(os.environ.get("CLICKHOUSE_PORT", "9000"))
        self.clickhouse_db: str = os.environ.get("CLICKHOUSE_DB", "banxe")
        self.kb_api_url: str = os.environ.get("BANXE_API_URL", "http://localhost:8000")


config = ExperimentConfig()
