"""
services/intent_layer/shadow.py — L1 Intent Layer PRODUCTION shadow-mode (FU-2 Phase 8).

Phase 5/6/7 stood up and instrumented a **staging** canary (Notifications +
Referral / CRM) behind ``INTENT_LAYER_ENABLED`` — prod stayed fully dark. Phase 8 is
the first *production* exposure, but a **shadow** one: a small, low-risk slice of prod
intent-like traffic is mirrored THROUGH the classifier + router (the same seam the
canary uses) purely to LOG and COMPARE what the Intent Layer *would* decide against the
mechanistic baseline that actually served the request. It performs **no live action**.

The hard guarantees (banking-safe, ADR-049 §D3):

  * **No live dispatch.** The shadow router is wired to :class:`NullShadowDispatcher`,
    which acknowledges nothing and calls no L2 mask, no producer, no L3 port, and writes
    no lineage. Even a resolved, in-scope intent only yields a *proposed* capability —
    never a payment, KYC write, CRM mutation or notification.
  * **Production-gated AND flag-gated.** Shadow runs only when
    ``INTENT_LAYER_SHADOW_ENABLED_PROD == true`` **and** ``BANXE_ENV == production``.
    Outside production the effective shadow scope is empty (a leaked flag is inert), so
    it can never interfere with the staging canary or with tests.
  * **High-risk stays blocked.** The Phase 7 ``is_high_risk_capability`` denylist is
    reused: high-risk capabilities are subtracted from the shadow allow-list (router
    holds them ``CANARY_HELD``) AND the Null dispatcher cannot act regardless.
  * **Never impacts the live response.** :meth:`ShadowPipeline.mirror` swallows every
    error/timeout (counted as ``shadow_error``) and returns ``None``; the caller's live
    path is untouched. The mirror is fire-and-forget.

R-SEC: only opaque governance labels are emitted — env, mode, capability, disposition,
a baseline-vs-shadow mismatch boolean and the correlation id. NEVER intent text, PII or
secrets. Callers pass a non-PII intent *descriptor* (e.g. an endpoint label), never raw
user content.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
import os
import uuid

from services.intent_layer.canary import is_high_risk_capability, normalize_capability
from services.intent_layer.catalog_snapshot import load_catalog
from services.intent_layer.classifier import IntentClassifier
from services.intent_layer.models import Disposition, DispositionKind
from services.intent_layer.observability import (
    CanaryMetricsPort,
    InMemoryCanaryMetrics,
    NullCanaryMetrics,
    canary_env,
)
from services.intent_layer.ports import (
    AgentDispatchPort,
    DispatchReceipt,
    DispatchRequest,
    NullLLMClassifier,
)
from services.intent_layer.router import IntentRouter

shadow_logger = logging.getLogger("banxe.intent_layer.shadow")

# ── Env flags ─────────────────────────────────────────────────────────────────────

SHADOW_ENABLED_ENV = "INTENT_LAYER_SHADOW_ENABLED_PROD"
SHADOW_CAPABILITIES_ENV = "INTENT_LAYER_SHADOW_CAPABILITIES"
SHADOW_SAMPLE_PCT_ENV = "INTENT_LAYER_SHADOW_SAMPLE_PCT"
BANXE_ENV_ENV = "BANXE_ENV"
PRODUCTION_ENV_VALUE = "production"

# The shadow slice mirrors the SAME low-risk surfaces the staging canary covers — it is
# never wider (FU-2 guardrail: no scope expansion beyond staging). Both are low-risk
# reads; high-risk capabilities are subtracted regardless of what is configured here.
DEFAULT_SHADOW_CAPABILITIES: tuple[str, ...] = ("Notifications", "Referral / CRM")

# Default fraction of the eligible slice to mirror when the flag is on but no explicit
# percentage is set: a deliberately tiny 1% (FU-2 step 1 decision).
DEFAULT_SHADOW_SAMPLE_PCT = 1

# ── Metric names (env=prod, mode=shadow — keep in lockstep with dashboards) ─────────

SHADOW_REQUESTS_TOTAL = "intent_layer_shadow_requests_total"
SHADOW_ERRORS_TOTAL = "intent_layer_shadow_errors_total"
SHADOW_MISMATCH_TOTAL = "intent_layer_shadow_baseline_vs_shadow_mismatch_total"


def shadow_env(env: dict[str, str] | None = None) -> str:
    """Deployment label gating shadow-mode. Reads ``BANXE_ENV``; blank → ``"unknown"``
    (a non-production value, so shadow stays off). Injectable env for deterministic tests."""
    source = env if env is not None else os.environ
    return (source.get(BANXE_ENV_ENV) or "unknown").strip().lower() or "unknown"


def shadow_enabled(env: dict[str, str] | None = None) -> bool:
    """Read ``INTENT_LAYER_SHADOW_ENABLED_PROD`` (default false). The master prod-shadow
    flag; the instant rollback lever is setting it back to false."""
    source = env if env is not None else os.environ
    return source.get(SHADOW_ENABLED_ENV, "false").strip().lower() == "true"


def shadow_active(env: dict[str, str] | None = None) -> bool:
    """True only when the flag is on AND the env is exactly ``production``.

    This is the single master gate the mirror hook checks first: it is the cheap,
    fail-closed short-circuit that keeps every non-prod path (staging canary, CI, dev)
    and every flag-off prod path entirely free of shadow work."""
    source = env if env is not None else os.environ
    return shadow_enabled(source) and shadow_env(source) == PRODUCTION_ENV_VALUE


def shadow_sample_pct(env: dict[str, str] | None = None) -> int:
    """The percentage [0, 100] of eligible requests to mirror. Defaults to a tiny 1%;
    a malformed value fails closed to 0 (mirror nothing) rather than mirroring all."""
    source = env if env is not None else os.environ
    raw = source.get(SHADOW_SAMPLE_PCT_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_SHADOW_SAMPLE_PCT
    try:
        return max(0, min(100, int(raw.strip())))
    except ValueError:
        return 0


def in_shadow_sample(correlation_id: str, pct: int) -> bool:
    """Deterministic per-correlation sampling: a stable hash of the id mod 100 < pct.

    Deterministic (not random) so the same request is always sampled the same way —
    reproducible, and a given trace either is or is not mirrored across retries."""
    if pct <= 0:
        return False
    if pct >= 100:
        return True
    digest = hashlib.sha256(correlation_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100 < pct


def shadow_capabilities(env: dict[str, str] | None = None) -> frozenset[str]:
    """The EFFECTIVE shadow allow-list as normalised capability keys for this env.

    Fail-closed, mirroring :func:`canary.canary_capabilities` but for production:
      1. **Production gate** — outside ``BANXE_ENV == production`` the allow-list is
         EMPTY (a leaked flag cannot widen the shadow anywhere else).
      2. **High-risk subtraction** — any high-risk capability is dropped, so a
         misconfigured allow-list can never admit a money/FX/KYC/etc surface."""
    source = env if env is not None else os.environ
    if shadow_env(source) != PRODUCTION_ENV_VALUE:
        return frozenset()
    raw = source.get(SHADOW_CAPABILITIES_ENV)
    labels = (
        DEFAULT_SHADOW_CAPABILITIES
        if raw is None
        else tuple(label.strip() for label in raw.split(",") if label.strip())
    )
    keys = {normalize_capability(label) for label in labels}
    return frozenset(key for key in keys if key and not is_high_risk_capability(key))


# ── Non-acting dispatcher ───────────────────────────────────────────────────────────


class NullShadowDispatcher(AgentDispatchPort):
    """An :class:`AgentDispatchPort` that NEVER acts. It is the mechanical guarantee
    behind "shadow performs no live action": no producer runs, no L2 mask is consulted,
    no L3 port is touched and no lineage is written — it just acknowledges the hand-off
    with a non-accepted, ``(shadow)`` receipt. Even a resolved, in-scope intent that
    reaches the dispatch boundary produces only a proposed capability, never an effect."""

    def dispatch(self, request: DispatchRequest) -> DispatchReceipt:
        return DispatchReceipt(
            accepted=False,
            agent="(shadow)",
            detail="shadow-mode: classified only, no live action (FU-2 Phase 8)",
            metadata={"mode": "shadow", "capability_key": normalize_capability(request.capability)},
        )


# ── Comparison + observer ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ShadowComparison:
    """The PII-minimised summary of one shadow mirror: what the baseline did vs what the
    Intent Layer would have proposed, and whether they differ."""

    baseline_capability: str
    shadow_disposition: str
    shadow_capability: str | None
    mismatch: bool
    correlation_id: str


class ShadowObserver:
    """Emits structured logs + metrics (tagged ``env=prod, mode=shadow``) for one shadow
    comparison. The metrics port defaults to the no-op sink, so a backend is touched only
    when one is wired; the structured log is always-on (no backend needed)."""

    def __init__(self, metrics: CanaryMetricsPort | None = None, *, env: str | None = None) -> None:
        self._metrics: CanaryMetricsPort = metrics if metrics is not None else NullCanaryMetrics()
        self._env = env if env is not None else canary_env()

    def _base(self, capability: str) -> dict[str, str]:
        return {"capability": capability, "env": self._env, "mode": "shadow"}

    def observe(self, comparison: ShadowComparison) -> None:
        base = self._base(comparison.shadow_capability or comparison.baseline_capability)
        self._metrics.incr(
            SHADOW_REQUESTS_TOTAL,
            labels={**base, "disposition": comparison.shadow_disposition},
        )
        if comparison.mismatch:
            self._metrics.incr(SHADOW_MISMATCH_TOTAL, labels=base)
        shadow_logger.info(
            "intent_layer.shadow env=%s mode=shadow disposition=%s baseline_capability=%s "
            "shadow_capability=%s mismatch=%s correlation_id=%s",
            self._env,
            comparison.shadow_disposition,
            comparison.baseline_capability,
            comparison.shadow_capability or "unresolved",
            str(comparison.mismatch).lower(),
            comparison.correlation_id,
        )

    def observe_error(self, baseline_capability: str, correlation_id: str, reason: str) -> None:
        self._metrics.incr(
            SHADOW_ERRORS_TOTAL,
            labels={"env": self._env, "mode": "shadow", "reason": reason},
        )
        shadow_logger.warning(
            "intent_layer.shadow env=%s mode=shadow error=%s baseline_capability=%s "
            "correlation_id=%s (swallowed — live response unaffected)",
            self._env,
            reason,
            baseline_capability,
            correlation_id,
        )


# ── Shadow pipeline ─────────────────────────────────────────────────────────────────


class ShadowPipeline:
    """Mirrors one prod intent through classify + route (with a non-acting dispatcher)
    and records the baseline-vs-shadow comparison. Construct per call (cheap: the
    catalogue load is the only cost) so flags are read fresh and rollback is instant."""

    def __init__(
        self,
        *,
        catalog=None,
        dispatcher: AgentDispatchPort | None = None,
        observer: ShadowObserver | None = None,
        env: str | None = None,
        capabilities: frozenset[str] | None = None,
    ) -> None:
        self._catalog = catalog if catalog is not None else load_catalog()
        self._dispatcher = dispatcher if dispatcher is not None else NullShadowDispatcher()
        self._env = env if env is not None else canary_env()
        self._observer = observer if observer is not None else ShadowObserver(env=self._env)
        self._capabilities = capabilities if capabilities is not None else shadow_capabilities()

    def mirror(
        self, intent_text: str, baseline_capability: str, correlation_id: str
    ) -> ShadowComparison | None:
        """Mirror one request. NEVER raises: any error is counted + logged and ``None``
        returned so the live caller is unaffected. Returns the comparison on success."""
        try:
            classifier = IntentClassifier(self._catalog, enabled=True, llm=NullLLMClassifier())
            resolved = classifier.classify(intent_text, correlation_id=correlation_id)
            router = IntentRouter(
                self._dispatcher, enabled=True, canary_capabilities=self._capabilities
            )
            disposition = router.route(resolved)
            comparison = _build_comparison(baseline_capability, disposition)
            self._observer.observe(comparison)
            return comparison
        except Exception as exc:  # noqa: BLE001 — shadow must never break the live path
            self._observer.observe_error(baseline_capability, correlation_id, type(exc).__name__)
            return None


def _build_comparison(baseline_capability: str, disposition: Disposition) -> ShadowComparison:
    """Diff the baseline routing against the shadow disposition. A mismatch = the Intent
    Layer would have classified the intent to a different capability than the mechanistic
    baseline (including resolving it to nothing — a governance event)."""
    shadow_capability = (
        disposition.capability
        if disposition.kind
        in (
            DispositionKind.DISPATCHED,
            DispositionKind.CANARY_HELD,
        )
        else None
    )
    mismatch = normalize_capability(baseline_capability) != normalize_capability(
        shadow_capability or ""
    )
    return ShadowComparison(
        baseline_capability=baseline_capability,
        shadow_disposition=disposition.kind.value,
        shadow_capability=shadow_capability,
        mismatch=mismatch,
        correlation_id=disposition.correlation_id,
    )


# ── Composition seam ────────────────────────────────────────────────────────────────


def get_shadow_metrics() -> CanaryMetricsPort:
    """Select the shadow metrics sink from ``CANARY_METRICS`` (same seam as the canary).

    Default (unset/``null``) → :class:`NullCanaryMetrics` (no-op): no backend touched.
    ``inmemory`` → a recordable sink for diagnostics. A real Prometheus/StatsD/ClickHouse
    port is injected here at the operator runtime step. Any other value fails closed."""
    choice = os.environ.get("CANARY_METRICS", "null").strip().lower()
    if choice in ("", "null", "none"):
        return NullCanaryMetrics()
    if choice == "inmemory":
        return InMemoryCanaryMetrics()
    raise ValueError(f"CANARY_METRICS={choice!r} is invalid; expected 'null' or 'inmemory'")


def maybe_mirror_intent(
    intent_text: str,
    baseline_capability: str,
    *,
    correlation_id: str | None = None,
    env: dict[str, str] | None = None,
) -> ShadowComparison | None:
    """Fire-and-forget hook for prod entrypoints. Mirrors the request into the shadow
    Intent Layer ONLY when shadow-mode is active in production AND the request falls in
    the sampled slice; otherwise it is a cheap no-op. Never raises, never alters the live
    response — call it after the live work, ignoring the return value.

    ``correlation_id`` is the trace key for deterministic sampling; a fresh opaque id is
    generated when the caller has none. ``intent_text`` MUST be a non-PII descriptor
    (e.g. an endpoint label), never raw user content (R-SEC)."""
    source = env if env is not None else os.environ
    if not shadow_active(source):
        return None
    cid = correlation_id or uuid.uuid4().hex
    if not in_shadow_sample(cid, shadow_sample_pct(source)):
        return None
    try:
        pipeline = ShadowPipeline(
            observer=ShadowObserver(get_shadow_metrics(), env=shadow_env(source)),
            env=shadow_env(source),
            capabilities=shadow_capabilities(source),
        )
    except Exception:  # noqa: BLE001 — construction must never break the live path
        shadow_logger.warning(
            "intent_layer.shadow construction failed correlation_id=%s "
            "(swallowed — live response unaffected)",
            cid,
        )
        return None
    return pipeline.mirror(intent_text, baseline_capability, cid)


__all__ = [
    "BANXE_ENV_ENV",
    "DEFAULT_SHADOW_CAPABILITIES",
    "DEFAULT_SHADOW_SAMPLE_PCT",
    "PRODUCTION_ENV_VALUE",
    "SHADOW_CAPABILITIES_ENV",
    "SHADOW_ENABLED_ENV",
    "SHADOW_ERRORS_TOTAL",
    "SHADOW_MISMATCH_TOTAL",
    "SHADOW_REQUESTS_TOTAL",
    "SHADOW_SAMPLE_PCT_ENV",
    "NullShadowDispatcher",
    "ShadowComparison",
    "ShadowObserver",
    "ShadowPipeline",
    "get_shadow_metrics",
    "in_shadow_sample",
    "maybe_mirror_intent",
    "shadow_active",
    "shadow_capabilities",
    "shadow_enabled",
    "shadow_env",
    "shadow_sample_pct",
]
