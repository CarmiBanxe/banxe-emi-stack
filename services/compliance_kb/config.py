"""
services/compliance_kb/config.py — Runtime configuration
IL-CKS-01 | banxe-emi-stack
"""

from __future__ import annotations

import os
from pathlib import Path


class KBConfig:
    """Runtime configuration for the compliance KB (injected from env)."""

    def __init__(self) -> None:
        self.chroma_persist_dir: str = os.environ.get(
            "CHROMA_PERSIST_DIR", str(Path("data/compliance_kb/chroma"))
        )
        self.embedding_model: str = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        self.kb_config_path: str = os.environ.get(
            "KB_CONFIG_PATH", str(Path("config/compliance_notebooks.yaml"))
        )
        self.api_port: int = int(os.environ.get("KB_API_PORT", "8098"))
        self.max_results: int = int(os.environ.get("KB_MAX_RESULTS", "10"))
        # nosemgrep: banxe-float-money — cosine similarity threshold, not a monetary value
        self.similarity_threshold: float = float(os.environ.get("KB_SIMILARITY_THRESHOLD", "0.7"))


# Singleton — override in tests by passing config explicitly
config = KBConfig()
