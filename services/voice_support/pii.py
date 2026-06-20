"""
services/voice_support/pii.py — Transcript PII redaction (Presidio)
GAP-069 | IMPL-3 | banxe-emi-stack

Redacts PII from transcripts BEFORE any persistence (UK GDPR data minimisation).
Uses Microsoft Presidio when installed; otherwise a deterministic regex fallback
covers the high-risk entities (email, phone, card PAN, IBAN, UK sort-code/account).
No raw audio or un-redacted transcript is ever stored downstream.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Deterministic fallback patterns (order matters — most specific first).
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    ("SORT_CODE", re.compile(r"\b\d{2}-\d{2}-\d{2}\b")),
    ("PHONE", re.compile(r"\b(?:\+?\d[\d ]{7,14}\d)\b")),
]


class PresidioRedactor:
    """PiiRedactorPort — Presidio when available, deterministic regex otherwise."""

    def __init__(self, use_presidio: bool = True) -> None:
        self._analyzer = None
        self._anonymizer = None
        if use_presidio:
            self._try_load_presidio()

    def _try_load_presidio(self) -> None:
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
        except ImportError:
            logger.info("Presidio not installed — using deterministic regex fallback")
            return
        self._analyzer = AnalyzerEngine()
        self._anonymizer = AnonymizerEngine()

    def redact(self, text: str) -> str:
        if self._analyzer is not None and self._anonymizer is not None:
            return self._redact_presidio(text)
        return self._redact_regex(text)

    def _redact_presidio(self, text: str) -> str:
        results = self._analyzer.analyze(text=text, language="en")  # type: ignore[union-attr]
        return self._anonymizer.anonymize(text=text, analyzer_results=results).text  # type: ignore[union-attr]

    @staticmethod
    def _redact_regex(text: str) -> str:
        redacted = text
        for label, pattern in _PATTERNS:
            redacted = pattern.sub(f"<REDACTED:{label}>", redacted)
        return redacted
