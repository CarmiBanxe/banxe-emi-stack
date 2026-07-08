"""Audit sampling (ADR-030 §9). Every RED decision path calls
``sampler.trace(decision_ref)``. R-SEC / ADR-021: a decision-ref is an opaque
REFERENCE (an id) — never a payload; no secrets/PII may pass through. InMemory is
the sandbox default (100% or configurable rate); Langfuse adapter = Outcome-C stub.
"""

from __future__ import annotations

import re
from typing import Protocol

from .errors import AuditPolicyError

# R-SEC guard: a ref must look like an id/reference, not a payload with PII/secret.
_UNSAFE = re.compile(r"@|[A-Za-z0-9+/=_\-]{41,}|(?i:secret|password|pan=|iban)")


def assert_ref_safe(decision_ref: str) -> None:
    if not decision_ref or len(decision_ref) > 128 or _UNSAFE.search(decision_ref):
        raise AuditPolicyError(
            "decision_ref must be an opaque id (no PII/secret/payload) — R-SEC/ADR-021")


class AuditSamplerPort(Protocol):
    def trace(self, decision_ref: str) -> bool: ...


class InMemorySampler:
    """Sandbox default. rate=1.0 ⇒ always trace. Deterministic by ref hash."""

    def __init__(self, rate: float = 1.0) -> None:
        if not 0.0 <= rate <= 1.0:
            raise AuditPolicyError("sample rate must be in [0,1]")
        self.rate = rate
        self.traces: list[str] = []

    def trace(self, decision_ref: str) -> bool:
        assert_ref_safe(decision_ref)  # fail-closed on unsafe refs
        sampled = self.rate >= 1.0 or (self._bucket(decision_ref) < int(self.rate * 100))
        if sampled:
            self.traces.append(decision_ref)
        return sampled

    @staticmethod
    def _bucket(ref: str) -> int:
        # deterministic 0..99 (not Python hash — stable across runs)
        return sum(ord(c) for c in ref) % 100


class LangfuseSampler:
    """Production adapter (Outcome-C)."""

    def trace(self, decision_ref: str) -> bool:
        assert_ref_safe(decision_ref)
        raise NotImplementedError(
            "Outcome-C: create a Langfuse trace/span keyed by decision_ref (ref only).")
