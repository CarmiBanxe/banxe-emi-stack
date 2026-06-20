"""
services/voice_support/asr.py — Faster-Whisper ASR adapter
GAP-069 | IMPL-3 | banxe-emi-stack

Speech-to-text via Faster-Whisper. The model is loaded lazily and only when
WHISPER_MODEL is configured; otherwise a safe-stub returns "" (no raw audio is
sent anywhere by default). Injectable so tests pass a fake transcript source.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class FasterWhisperAsr:
    """AsrPort — Faster-Whisper transcription (safe-stub when no model)."""

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or os.environ.get("WHISPER_MODEL", "")
        self._model: object | None = None

    def _load(self) -> None:
        if self._model is not None or not self._model_name:
            return
        from faster_whisper import WhisperModel  # lazy — optional dependency

        self._model = WhisperModel(self._model_name)

    def transcribe(self, audio: bytes) -> str:
        self._load()
        if self._model is None:
            logger.info("Whisper not configured — empty transcript (safe-stub)")
            return ""
        segments, _info = self._model.transcribe(audio)  # type: ignore[attr-defined]
        return " ".join(segment.text.strip() for segment in segments).strip()
