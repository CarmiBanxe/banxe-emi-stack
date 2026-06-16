#!/usr/bin/env python3
"""
scripts/intent_layer_dryrun.py — DEVELOPER TOOL (NOT a production entrypoint).

Dry-run harness for the ADR-049 L1 Intent Layer. It drives a single client intent
through the SAME internal entrypoint the HTTP handler uses (catalog → classifier →
router) and reports what L1 would do — WITHOUT performing any real dispatch.

Safety contract (FU-2 Phase 3 — dark mode):
  * Respects ``INTENT_LAYER_ENABLED`` (default false). While false the report shows the
    inert ``NOT_ENABLED`` disposition exactly as the live layer returns it.
  * ``--force-simulate`` flips the *report* to show what WOULD happen if the layer were
    enabled — but the dispatcher is an inert simulator that NEVER calls a real L2 mask,
    a payment-core adapter, the network, or ClickHouse. No external side effect, ever.
  * No new public endpoint, no live infra — a local CLI only.

Usage::

    echo '{"intent_text": "send money to Alice"}' | python scripts/intent_layer_dryrun.py
    python scripts/intent_layer_dryrun.py --intent "freeze my card"
    python scripts/intent_layer_dryrun.py --file intent.json --force-simulate --json
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import sys

# Allow running as a bare script (``python scripts/intent_layer_dryrun.py``) by
# putting the repo root on the path before importing the services package.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from services.intent_layer.catalog_snapshot import load_catalog  # noqa: E402
from services.intent_layer.classifier import IntentClassifier  # noqa: E402
from services.intent_layer.config import intent_layer_enabled  # noqa: E402
from services.intent_layer.models import DispositionKind, ResolvedIntent  # noqa: E402
from services.intent_layer.ports import DispatchReceipt, DispatchRequest  # noqa: E402
from services.intent_layer.router import IntentRouter  # noqa: E402


class _SimulatingDispatcher:
    """Inert ``AgentDispatchPort`` for the dry-run: it performs NO work — no L2 mask,
    no adapter, no network, no ClickHouse — and returns an honest 'simulated' receipt.
    This keeps the real router/gate logic on the code path while guaranteeing zero
    external side effects, even under ``--force-simulate``."""

    def __init__(self) -> None:
        self.calls = 0

    def dispatch(self, request: DispatchRequest) -> DispatchReceipt:
        self.calls += 1
        return DispatchReceipt(
            accepted=False,
            agent="(dry-run-simulated)",
            detail="dry-run: no real dispatch performed",
            metadata={"simulated": "true", "capability": request.capability},
        )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="intent_layer_dryrun",
        description="DEV TOOL: dry-run the L1 Intent Layer with no real dispatch.",
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--intent", help="Free-form client intent text.")
    src.add_argument("--file", help="Path to a JSON file: {intent_text, correlation_id?}.")
    parser.add_argument("--correlation-id", help="Optional trace id (generated when absent).")
    parser.add_argument(
        "--force-simulate",
        action="store_true",
        help="Report what WOULD happen if enabled. Still performs NO real dispatch.",
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    return parser.parse_args(argv)


def _read_intent(args: argparse.Namespace) -> tuple[str, str | None]:
    """Resolve the intent text + optional correlation id from --intent / --file / stdin."""
    if args.intent is not None:
        return args.intent, args.correlation_id
    if args.file is not None:
        with open(args.file, encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload["intent_text"], payload.get("correlation_id", args.correlation_id)
    raw = sys.stdin.read().strip()
    if not raw:
        raise SystemExit("no intent supplied (use --intent, --file, or pipe JSON/text on stdin)")
    if raw.startswith("{"):
        payload = json.loads(raw)
        return payload["intent_text"], payload.get("correlation_id", args.correlation_id)
    return raw, args.correlation_id


@dataclass(frozen=True)
class _Report:
    intent_text: str
    correlation_id: str
    flag_enabled: bool
    force_simulate: bool
    resolved: ResolvedIntent
    disposition_kind: DispositionKind


def _build_report(intent_text: str, correlation_id: str | None, *, force_simulate: bool) -> _Report:
    """Run classify → route through the real layer with an inert dispatcher."""
    flag_enabled = intent_layer_enabled()
    effective = flag_enabled or force_simulate
    catalog = load_catalog()
    classifier = IntentClassifier(catalog, enabled=effective)  # NullLLM → no live LLM
    router = IntentRouter(_SimulatingDispatcher(), enabled=effective)
    resolved = classifier.classify(intent_text, correlation_id=correlation_id)
    disposition = router.route(resolved)
    return _Report(
        intent_text=intent_text,
        correlation_id=resolved.correlation_id,
        flag_enabled=flag_enabled,
        force_simulate=force_simulate,
        resolved=resolved,
        disposition_kind=disposition.kind,
    )


def _report_dict(report: _Report) -> dict[str, object]:
    r = report.resolved
    return {
        "intent_text": report.intent_text,
        "correlation_id": report.correlation_id,
        "INTENT_LAYER_ENABLED": report.flag_enabled,
        "mode": "SIMULATE"
        if (report.force_simulate and not report.flag_enabled)
        else ("ENABLED" if report.flag_enabled else "DARK"),
        "classification": {
            "status": r.status.value,
            "matched_intent": r.matched_intent,
            "capability": r.capability,
            "confidence": r.confidence,
            "band": r.band.value,
            "match_source": r.match_source.value,
            "process_refs": [f"{p.process_id}@{p.version}" for p in r.process_refs],
        },
        "disposition": report.disposition_kind.value,
        "would_dispatch_if_enabled": r.is_resolved,
        "real_dispatch_performed": False,
    }


def _render_human(report: _Report) -> str:
    d = _report_dict(report)
    c = d["classification"]
    refs = ", ".join(c["process_refs"]) or "—"  # type: ignore[arg-type]
    return "\n".join(
        [
            "=== Intent Layer dry-run (DEV TOOL — no real dispatch) ===",
            f"intent_text          : {d['intent_text']!r}",
            f"correlation_id       : {d['correlation_id']}",
            f"INTENT_LAYER_ENABLED : {str(d['INTENT_LAYER_ENABLED']).lower()}  (actual env flag)",
            f"mode                 : {d['mode']}",
            "-- classification --",
            f"  status             : {c['status']}",
            f"  matched_intent     : {c['matched_intent']}",
            f"  capability / mask  : {c['capability']}",
            f"  confidence / band  : {c['confidence']:.2f} / {c['band']}",
            f"  match_source       : {c['match_source']}",
            f"  process_refs       : {refs}",
            "-- routing --",
            f"  disposition        : {d['disposition']}",
            f"  would dispatch if enabled : {'yes' if d['would_dispatch_if_enabled'] else 'no'}",
            "  real dispatch performed   : NO (dry-run never touches a mask/adapter/ClickHouse)",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    intent_text, correlation_id = _read_intent(args)
    report = _build_report(intent_text, correlation_id, force_simulate=args.force_simulate)
    if args.json:
        print(json.dumps(_report_dict(report), indent=2))
    else:
        print(_render_human(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
