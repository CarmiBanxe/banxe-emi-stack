"""
services/design_pipeline/token_extractor.py — Design Token Pipeline
IL-D2C-01 | BANXE EMI AI Bank

Extracts design tokens from Penpot via PenpotPort,
transforms them to Style Dictionary format, and writes output files.

Output targets (via style-dictionary):
  - config/design-tokens/output/banxe-tokens.css   (CSS custom properties)
  - config/design-tokens/output/tailwind-tokens.js (Tailwind theme extension)
  - config/design-tokens/output/tokens.json        (raw JSON for RN)
  - config/design-tokens/output/tokens.rn.ts       (React Native StyleSheet)
  - config/design-tokens/output/_tokens.scss        (SCSS variables)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import subprocess
from typing import Any

from services.design_pipeline.models import DesignTokenSet, TokenSyncResult
from services.design_pipeline.penpot_client import PenpotPort

logger = logging.getLogger("banxe.design_pipeline.token_extractor")

_TOKENS_BASE = Path("config/design-tokens")
_TOKENS_OUTPUT = _TOKENS_BASE / "output"
_STYLE_DICT_CONFIG = _TOKENS_BASE / "style-dictionary.config.json"
_BANXE_TOKENS_FILE = _TOKENS_BASE / "banxe-tokens.json"


class TokenExtractionError(Exception):
    """Raised when token extraction fails."""

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.context = context or {}


class TokenExtractor:
    """
    Extracts tokens from Penpot and transforms them to Style Dictionary format.

    Protocol DI pattern: accepts any PenpotPort implementation,
    enabling InMemoryPenpotClient for unit tests.
    """

    def __init__(
        self,
        penpot_client: PenpotPort,
        output_dir: Path | str | None = None,
        style_dict_cli: str = "npx style-dictionary",
    ) -> None:
        self._client = penpot_client
        self._output_dir = Path(output_dir) if output_dir else _TOKENS_OUTPUT
        self._style_dict_cli = style_dict_cli

    async def extract_from_penpot(self, file_id: str) -> DesignTokenSet:
        """Pull the latest tokens from a Penpot file."""
        logger.info("Extracting design tokens from file_id=%s", file_id)
        try:
            token_set = await self._client.get_design_tokens(file_id)
        except Exception as exc:
            raise TokenExtractionError(
                f"Failed to fetch tokens from Penpot: {exc}",
                context={"file_id": file_id},
            ) from exc

        logger.info(
            "Extracted %d colours, %d typography, %d spacing tokens",
            len(token_set.colors),
            len(token_set.typography),
            len(token_set.spacing),
        )
        return token_set

    def export_to_style_dictionary(self, token_set: DesignTokenSet) -> Path:
        """
        Write tokens to the banxe-tokens.json file in Style Dictionary format.

        Returns the path of the written JSON file.
        """
        sd_dict = token_set.to_style_dictionary_format()

        # Merge with existing static tokens (don't overwrite defaults if Penpot
        # returns empty — retain the curated static tokens as baseline)
        if _BANXE_TOKENS_FILE.exists():
            with _BANXE_TOKENS_FILE.open("r") as f:
                existing = json.load(f)
            for category, tokens in sd_dict.items():
                if tokens:  # Only override if Penpot returned data
                    existing[category] = tokens
            sd_dict = existing

        _BANXE_TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _BANXE_TOKENS_FILE.open("w") as f:
            json.dump(sd_dict, f, indent=2)

        logger.info("Wrote Style Dictionary JSON to %s", _BANXE_TOKENS_FILE)
        return _BANXE_TOKENS_FILE

    def build_style_dictionary(self) -> list[str]:
        """
        Run the Style Dictionary CLI to generate all output files.

        Returns list of output file paths.

        Requires Node.js and style-dictionary npm package:
          npm install -g style-dictionary
          # or use npx (zero-install)
        """
        config_path = str(_STYLE_DICT_CONFIG)
        cmd = f"{self._style_dict_cli} build --config {config_path}"
        logger.info("Running: %s", cmd)

        result = subprocess.run(
            cmd,
            shell=True,  # noqa: S602
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            raise TokenExtractionError(
                f"Style Dictionary build failed: {result.stderr}",
                context={"cmd": cmd, "stdout": result.stdout},
            )

        logger.info("Style Dictionary output:\n%s", result.stdout)

        # Return list of generated output files
        output_files = []
        for pattern in ["*.css", "*.js", "*.json", "*.ts", "*.scss"]:
            output_files.extend(str(p) for p in self._output_dir.glob(pattern))
        return output_files

    async def sync(self, file_id: str) -> TokenSyncResult:
        """
        Full sync: Penpot → Style Dictionary → output files.

        Returns a TokenSyncResult with counts and output file paths.
        """
        errors: list[str] = []

        # Step 1: Extract from Penpot
        try:
            token_set = await self.extract_from_penpot(file_id)
        except TokenExtractionError as exc:
            return TokenSyncResult(
                file_id=file_id,
                tokens_extracted=0,
                errors=[str(exc)],
            )

        tokens_count = len(token_set.colors) + len(token_set.typography) + len(token_set.spacing)

        # Step 2: Write to JSON
        try:
            self.export_to_style_dictionary(token_set)
        except Exception as exc:
            errors.append(f"Failed to write token JSON: {exc}")

        # Step 3: Build Style Dictionary output
        output_files: list[str] = []
        try:
            output_files = self.build_style_dictionary()
        except TokenExtractionError as exc:
            errors.append(f"Style Dictionary build: {exc}")
        except FileNotFoundError:
            errors.append(
                "Style Dictionary CLI not found. Install: npm install -g style-dictionary"
            )

        return TokenSyncResult(
            file_id=file_id,
            tokens_extracted=tokens_count,
            output_files=output_files,
            errors=errors,
        )

    # ── Token introspection helpers ───────────────────────────────────────────

    @staticmethod
    def load_current_tokens() -> dict[str, Any]:
        """Read the current banxe-tokens.json from disk."""
        if not _BANXE_TOKENS_FILE.exists():
            return {}
        with _BANXE_TOKENS_FILE.open("r") as f:
            return json.load(f)

    @staticmethod
    def token_count() -> int:
        """Count tokens across all categories in the current banxe-tokens.json."""
        tokens = TokenExtractor.load_current_tokens()
        return sum(len(v) for v in tokens.values() if isinstance(v, dict))

    @staticmethod
    def get_css_variable(token_path: str) -> str:
        """
        Convert a dot-path token reference to a CSS custom property name.

        Example: "color.primary" → "var(--banxe-color-primary)"
        """
        parts = token_path.replace(".", "-")
        return f"var(--banxe-{parts})"
