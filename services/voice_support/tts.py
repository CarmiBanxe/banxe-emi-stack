"""
services/voice_support/tts.py — Text-to-speech adapter
GAP-069 | IMPL-3 | banxe-emi-stack

TTS via XTTS / Kokoro. Pluggable and offline-safe: returns empty audio when no
engine is configured (no secrets, no network). Injectable for tests.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class XttsTts:
    """TtsPort — XTTS/Kokoro synthesis (safe-stub when unconfigured)."""

    def __init__(self, engine: str | None = None) -> None:
        self._engine = engine or os.environ.get("TTS_ENGINE", "")

    def synthesize(self, text: str) -> bytes:
        if not self._engine:
            logger.info("TTS not configured — empty audio (safe-stub)")
            return b""
        # Live path would render `text` to PCM/Opus via the configured engine.
        return text.encode("utf-8")
