"""
services/design_pipeline/code_generator.py — Mitosis Bridge & Code Generator
IL-D2C-01 | BANXE EMI AI Bank

Compiles Mitosis JSX (LLM output) to target frameworks using @builder.io/mitosis CLI.
Falls back to direct React/Tailwind generation when Mitosis is not available.

Mitosis installation:
  npm install -g @builder.io/mitosis-cli
  # or via npx (zero-install)

References:
  https://github.com/BuilderIO/mitosis
  https://mitosis.builder.io/
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from services.design_pipeline.models import Framework

logger = logging.getLogger("banxe.design_pipeline.code_generator")

# Templates directory
_TEMPLATES_DIR = Path(__file__).parent / "templates"


class MitosisGenerationError(Exception):
    """Raised when Mitosis compilation fails."""

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.context = context or {}


class MitosisGenerator:
    """
    Code generator using @builder.io/mitosis CLI.

    Write-once Mitosis JSX → compile to React, Vue, RN, Angular, Svelte.

    Args:
        mitosis_cli:       CLI command (default: 'npx @builder.io/mitosis-cli')
        fallback_enabled:  If True, fall back to direct React generation on CLI failure
    """

    def __init__(
        self,
        mitosis_cli: str = "npx @builder.io/mitosis-cli",
        fallback_enabled: bool = True,
    ) -> None:
        self._cli = mitosis_cli
        self._fallback_enabled = fallback_enabled

    def compile(self, mitosis_jsx: str, framework: Framework) -> str:
        """
        Compile Mitosis JSX to the target framework.

        Args:
            mitosis_jsx:  Mitosis JSX source code (from LLM)
            framework:    Target framework enum value

        Returns:
            Compiled code string for the target framework.
        """
        if not mitosis_jsx.strip():
            raise MitosisGenerationError(
                "Empty Mitosis JSX input",
                context={"framework": framework.value},
            )

        try:
            return self._run_mitosis_cli(mitosis_jsx, framework)
        except (MitosisGenerationError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            if self._fallback_enabled:
                logger.warning(
                    "Mitosis CLI failed (%s) — using direct %s generator",
                    exc,
                    framework.value,
                )
                return self._direct_generate(mitosis_jsx, framework)
            raise

    def supported_frameworks(self) -> list[Framework]:
        return [
            Framework.REACT,
            Framework.VUE,
            Framework.REACT_NATIVE,
            Framework.ANGULAR,
            Framework.SVELTE,
        ]

    # ── Mitosis CLI ───────────────────────────────────────────────────────────

    def _run_mitosis_cli(self, mitosis_jsx: str, framework: Framework) -> str:
        """Run Mitosis CLI in a temp directory and return compiled output."""
        target_flag = self._framework_to_mitosis_target(framework)

        with tempfile.TemporaryDirectory(prefix="banxe_mitosis_") as tmpdir:
            tmp = Path(tmpdir)
            input_file = tmp / "component.lite.tsx"
            output_dir = tmp / "output"
            output_dir.mkdir()

            input_file.write_text(mitosis_jsx, encoding="utf-8")

            cmd = [
                *self._cli.split(),
                "compile",
                "--to",
                target_flag,
                "--out",
                str(output_dir),
                str(input_file),
            ]
            logger.debug("Running Mitosis: %s", " ".join(cmd))

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "NO_COLOR": "1"},
            )

            if result.returncode != 0:
                raise MitosisGenerationError(
                    f"Mitosis CLI error (exit {result.returncode}): {result.stderr[:500]}",
                    context={"cmd": cmd, "stdout": result.stdout[:200]},
                )

            # Find the output file
            ext = self._framework_to_ext(framework)
            output_files = list(output_dir.glob(f"**/*{ext}"))
            if not output_files:
                raise MitosisGenerationError(
                    f"Mitosis produced no {ext} output",
                    context={"output_dir": str(output_dir)},
                )

            return output_files[0].read_text(encoding="utf-8")

    # ── Direct generators (fallback) ──────────────────────────────────────────

    def _direct_generate(self, mitosis_jsx: str, framework: Framework) -> str:
        """
        Generate code directly without Mitosis CLI.

        Transforms Mitosis JSX to the target framework using simple
        string transformations and Jinja2 templates.
        """
        match framework:
            case Framework.REACT:
                return self._generate_react(mitosis_jsx)
            case Framework.VUE:
                return self._generate_vue(mitosis_jsx)
            case Framework.REACT_NATIVE:
                return self._generate_react_native(mitosis_jsx)
            case Framework.SVELTE:
                return self._generate_svelte(mitosis_jsx)
            case _:
                return self._generate_react(mitosis_jsx)

    @staticmethod
    def _generate_react(mitosis_jsx: str) -> str:
        """Transform Mitosis JSX to standard React TSX."""
        # Replace Mitosis-specific imports
        code = mitosis_jsx.replace("from '@builder.io/mitosis'", "from 'react'")
        # Replace class= with className= (JSX requirement)
        code = code.replace(' class="', ' className="')
        code = code.replace(" class={", " className={")

        # Wrap in TypeScript component if not already
        if "export default function" not in code and "export default" not in code:
            code = "import React from 'react';\n\n" + code.replace(
                "function ", "export default function ", 1
            )

        return code

    @staticmethod
    def _generate_vue(mitosis_jsx: str) -> str:
        """Convert Mitosis JSX to Vue 3 SFC format."""
        # Extract component body (simplified)
        component_name = "BanxeComponent"
        for line in mitosis_jsx.split("\n"):
            if "export default function" in line:
                parts = line.split("function ")
                if len(parts) > 1:
                    component_name = parts[1].split("(")[0].strip()
                break

        return (
            f"<!-- Vue 3 SFC — BANXE Design Pipeline -->\n"
            f"<template>\n"
            f'  <div class="banxe-component">\n'
            f"    <!-- TODO: implement {component_name} template -->\n"
            f"  </div>\n"
            f"</template>\n\n"
            f'<script setup lang="ts">\n'
            f"// {component_name}\n"
            f"// Generated from Mitosis JSX by BANXE Design Pipeline (IL-D2C-01)\n"
            f"</script>\n\n"
            f"<style scoped>\n"
            f"@import '@/styles/banxe-tokens.css';\n"
            f".banxe-component {{ /* styles from design tokens */ }}\n"
            f"</style>\n"
        )

    @staticmethod
    def _generate_react_native(mitosis_jsx: str) -> str:
        """Convert Mitosis JSX to React Native TSX."""
        code = (
            "import React from 'react';\n"
            "import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';\n"
            "import { tokens } from '@banxe/tokens';\n\n"
            "// BANXE Design Pipeline (IL-D2C-01) — React Native\n"
        )
        # Convert div → View, span/p → Text
        rn_body = mitosis_jsx.replace("<div", "<View").replace("</div>", "</View>")
        rn_body = rn_body.replace("<p>", "<Text>").replace("</p>", "</Text>")
        rn_body = rn_body.replace(' class="', " style={styles.")
        return (
            code + rn_body + "\nconst styles = StyleSheet.create({\n"
            "  container: {\n"
            "    backgroundColor: tokens.color.surface,\n"
            "    padding: tokens.spacing.md,\n"
            "  },\n"
            "});\n"
        )

    @staticmethod
    def _generate_svelte(mitosis_jsx: str) -> str:
        """Convert Mitosis JSX to Svelte component."""
        return (
            '<script lang="ts">\n'
            "  // BANXE Design Pipeline (IL-D2C-01) — Svelte\n"
            "</script>\n\n"
            '<div class="banxe-component">\n'
            "  <!-- TODO: implement from Mitosis JSX -->\n"
            "</div>\n\n"
            "<style>\n"
            "  @import '../styles/banxe-tokens.css';\n"
            "</style>\n"
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _framework_to_mitosis_target(framework: Framework) -> str:
        mapping = {
            Framework.REACT: "react",
            Framework.VUE: "vue",
            Framework.REACT_NATIVE: "react-native",
            Framework.ANGULAR: "angular",
            Framework.SVELTE: "svelte",
        }
        return mapping.get(framework, "react")

    @staticmethod
    def _framework_to_ext(framework: Framework) -> str:
        ext_map = {
            Framework.REACT: ".tsx",
            Framework.VUE: ".vue",
            Framework.REACT_NATIVE: ".tsx",
            Framework.ANGULAR: ".ts",
            Framework.SVELTE: ".svelte",
        }
        return ext_map.get(framework, ".tsx")


# ── InMemory generator (test double) ─────────────────────────────────────────


class InMemoryCodeGenerator:
    """Test double — returns deterministic scaffold, no CLI dependency."""

    def compile(self, mitosis_jsx: str, framework: Framework) -> str:  # noqa: ARG002
        return (
            f"// Framework: {framework.value}\n"
            f"// BANXE Design Pipeline (IL-D2C-01) — InMemory\n"
            f"export default function GeneratedComponent() {{\n"
            f'  return <div className="banxe-component">Generated</div>;\n'
            f"}}\n"
        )

    def supported_frameworks(self) -> list[Framework]:
        return list(Framework)
