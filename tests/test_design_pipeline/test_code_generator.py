"""
tests/test_design_pipeline/test_code_generator.py
IL-D2C-01 — Mitosis code generator tests
"""

from __future__ import annotations

import pytest

from services.design_pipeline.code_generator import (
    InMemoryCodeGenerator,
    MitosisGenerationError,
    MitosisGenerator,
)
from services.design_pipeline.models import Framework

_SAMPLE_MITOSIS_JSX = """\
import { useState } from '@builder.io/mitosis';

export default function MyButton({ label }: { label: string }) {
  return (
    <button class="banxe-btn banxe-btn--primary" onClick={() => {}}>
      {label}
    </button>
  );
}
"""


class TestInMemoryCodeGenerator:
    """Tests for InMemoryCodeGenerator — no CLI required."""

    def test_compile_returns_string(self) -> None:
        gen = InMemoryCodeGenerator()
        result = gen.compile(_SAMPLE_MITOSIS_JSX, Framework.REACT)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_compile_mentions_framework(self) -> None:
        gen = InMemoryCodeGenerator()
        result = gen.compile(_SAMPLE_MITOSIS_JSX, Framework.VUE)
        assert "vue" in result.lower()

    def test_compile_react_native(self) -> None:
        gen = InMemoryCodeGenerator()
        result = gen.compile(_SAMPLE_MITOSIS_JSX, Framework.REACT_NATIVE)
        assert "react-native" in result.lower()

    def test_compile_svelte(self) -> None:
        gen = InMemoryCodeGenerator()
        result = gen.compile(_SAMPLE_MITOSIS_JSX, Framework.SVELTE)
        assert "svelte" in result.lower()

    def test_compile_angular(self) -> None:
        gen = InMemoryCodeGenerator()
        result = gen.compile(_SAMPLE_MITOSIS_JSX, Framework.ANGULAR)
        assert isinstance(result, str)

    def test_supported_frameworks_returns_all(self) -> None:
        gen = InMemoryCodeGenerator()
        supported = gen.supported_frameworks()
        assert Framework.REACT in supported
        assert Framework.VUE in supported
        assert Framework.REACT_NATIVE in supported

    def test_compile_includes_il_reference(self) -> None:
        gen = InMemoryCodeGenerator()
        result = gen.compile(_SAMPLE_MITOSIS_JSX, Framework.REACT)
        assert "IL-D2C-01" in result


class TestMitosisGeneratorDirectGenerators:
    """Test direct generators (fallback path, no CLI)."""

    def test_generate_react_replaces_class_with_classname(self) -> None:
        jsx = '<div class="banxe-btn">Click</div>'
        result = MitosisGenerator._generate_react(jsx)
        assert 'className="banxe-btn"' in result

    def test_generate_react_replaces_mitosis_import(self) -> None:
        jsx = "import { useState } from '@builder.io/mitosis';"
        result = MitosisGenerator._generate_react(jsx)
        assert "from 'react'" in result
        assert "@builder.io/mitosis" not in result

    def test_generate_vue_contains_template_tag(self) -> None:
        result = MitosisGenerator._generate_vue("// some code")
        assert "<template>" in result
        assert "<script" in result

    def test_generate_vue_contains_style_scoped(self) -> None:
        result = MitosisGenerator._generate_vue("// code")
        assert "<style scoped>" in result

    def test_generate_react_native_contains_rn_imports(self) -> None:
        result = MitosisGenerator._generate_react_native("// code")
        assert "react-native" in result
        assert "StyleSheet" in result

    def test_generate_svelte_contains_script_lang(self) -> None:
        result = MitosisGenerator._generate_svelte("// code")
        assert '<script lang="ts">' in result

    def test_framework_to_ext_react(self) -> None:
        assert MitosisGenerator._framework_to_ext(Framework.REACT) == ".tsx"

    def test_framework_to_ext_vue(self) -> None:
        assert MitosisGenerator._framework_to_ext(Framework.VUE) == ".vue"

    def test_framework_to_ext_svelte(self) -> None:
        assert MitosisGenerator._framework_to_ext(Framework.SVELTE) == ".svelte"

    def test_framework_to_ext_rn(self) -> None:
        assert MitosisGenerator._framework_to_ext(Framework.REACT_NATIVE) == ".tsx"

    def test_framework_to_mitosis_target_react(self) -> None:
        assert MitosisGenerator._framework_to_mitosis_target(Framework.REACT) == "react"

    def test_framework_to_mitosis_target_vue(self) -> None:
        assert MitosisGenerator._framework_to_mitosis_target(Framework.VUE) == "vue"

    def test_framework_to_mitosis_target_rn(self) -> None:
        assert (
            MitosisGenerator._framework_to_mitosis_target(Framework.REACT_NATIVE) == "react-native"
        )


class TestMitosisGeneratorFallback:
    """MitosisGenerator with fallback_enabled=True falls back on CLI failure."""

    def test_compile_falls_back_when_cli_missing(self) -> None:
        gen = MitosisGenerator(
            mitosis_cli="nonexistent_command_that_fails",
            fallback_enabled=True,
        )
        result = gen.compile(_SAMPLE_MITOSIS_JSX, Framework.REACT)
        # Should fall back to direct React generation without raising
        assert isinstance(result, str)
        assert len(result) > 0

    def test_compile_empty_jsx_raises(self) -> None:
        gen = MitosisGenerator(fallback_enabled=False)
        with pytest.raises(MitosisGenerationError, match="Empty Mitosis JSX"):
            gen.compile("   ", Framework.REACT)

    def test_compile_whitespace_only_raises(self) -> None:
        gen = MitosisGenerator(fallback_enabled=False)
        with pytest.raises(MitosisGenerationError):
            gen.compile("\n\t\n", Framework.REACT)

    def test_supported_frameworks_includes_react(self) -> None:
        gen = MitosisGenerator()
        assert Framework.REACT in gen.supported_frameworks()

    def test_mitosis_generation_error_has_context(self) -> None:
        err = MitosisGenerationError("test", context={"cmd": ["mitosis"]})
        assert "test" in str(err)
        assert err.context["cmd"] == ["mitosis"]
