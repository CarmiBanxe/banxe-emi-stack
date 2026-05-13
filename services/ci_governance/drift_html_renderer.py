"""
drift_html_renderer.py — Static HTML report from S16.9 drift history (S16.12).

Renders the append-only JSONL history into a single static HTML5 page that
operators can open in any browser. No server, no JS, no external assets.

Design constraints:
  - READ-ONLY against history JSONL — never mutates it.
  - Atomic write: tmpfile in same dir + os.replace (matches S16.8 pattern).
  - All user-controlled fields pass through html.escape() — XSS-safe.
  - Empty history → valid HTML with "no entries" placeholder; success=True.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import html
import os
from pathlib import Path
import time

from services.ci_governance.drift_history_store import DriftHistoryStore

FileWriter = Callable[[str, str], None]


@dataclass(frozen=True)
class RenderResult:
    """Outcome of a single render operation."""

    success: bool
    report_path: str
    rendered_at: float
    entries_rendered: int
    byte_size: int | None = None
    error: str | None = None


def _default_file_writer(target_path: str, body: str) -> None:
    """Atomic write: tmpfile sibling -> os.replace."""
    target = Path(target_path)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp = parent / f"{target.name}.tmp.{os.getpid()}.{int(time.time_ns())}"
    try:
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()


_STYLE = """\
body{font-family:system-ui,sans-serif;margin:2em;background:#fafafa;color:#222}
h1{font-size:1.4em}
.meta{color:#666;font-size:.85em;margin-bottom:1.5em}
.cards{display:flex;gap:1em;flex-wrap:wrap;margin-bottom:1.5em}
.card{background:#fff;border:1px solid #ddd;border-radius:6px;padding:1em 1.4em;min-width:140px}
.card .val{font-size:1.6em;font-weight:700}
.card .lbl{font-size:.8em;color:#888}
table{border-collapse:collapse;width:100%;font-size:.88em}
th,td{border:1px solid #ddd;padding:6px 10px;text-align:left}
th{background:#f0f0f0}
tr:nth-child(even){background:#f9f9f9}
.badge{display:inline-block;padding:2px 8px;border-radius:3px;font-size:.8em;font-weight:600}
.badge-yes{background:#fee;color:#c00}
.badge-no{background:#efe;color:#060}
.empty{text-align:center;padding:3em;color:#999;font-style:italic}
"""


def _badge(value: bool) -> str:
    cls = "badge-yes" if value else "badge-no"
    text = "YES" if value else "no"
    return f'<span class="badge {cls}">{text}</span>'


def _ts_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _render_html(
    entries: list[dict],
    window_seconds: int,
    rendered_at: float,
) -> str:
    rendered_iso = _ts_iso(rendered_at)
    drift_count = sum(1 for e in entries if e.get("drift_detected") is True)
    strict_count = sum(1 for e in entries if e.get("strict_weakened") is True)
    latest_ts = max((e.get("ts", 0) for e in entries), default=0.0)
    latest_iso = _ts_iso(latest_ts) if latest_ts > 0 else "n/a"

    parts: list[str] = []
    parts.append("<!doctype html>")
    parts.append('<html lang="en"><head>')
    parts.append('<meta charset="utf-8">')
    parts.append("<title>Banxe CI drift report</title>")
    parts.append(f"<style>{_STYLE}</style>")
    parts.append("</head><body>")
    parts.append("<h1>Banxe CI drift report</h1>")
    parts.append(
        f'<div class="meta">Generated: {rendered_iso} &middot; '
        f"Window: {window_seconds}s &middot; "
        f"Entries: {len(entries)}</div>"
    )

    # Summary cards
    parts.append('<div class="cards">')
    for label, val in [
        ("Total events", str(len(entries))),
        ("Drift detected", str(drift_count)),
        ("Strict weakened", str(strict_count)),
        ("Latest check", latest_iso),
    ]:
        parts.append(
            f'<div class="card"><div class="val">{html.escape(val)}</div>'
            f'<div class="lbl">{html.escape(label)}</div></div>'
        )
    parts.append("</div>")

    # Table
    if entries:
        parts.append("<table><thead><tr>")
        for hdr in [
            "Timestamp",
            "Drift",
            "Missing contexts",
            "Extra contexts",
            "Strict weakened",
            "Summary",
        ]:
            parts.append(f"<th>{hdr}</th>")
        parts.append("</tr></thead><tbody>")
        for e in entries:
            ts_str = _ts_iso(e.get("ts", 0))
            drift = e.get("drift_detected", False)
            missing = ", ".join(html.escape(str(c)) for c in e.get("missing_rules", []))
            extra = ", ".join(html.escape(str(c)) for c in e.get("extra_rules", []))
            strict = e.get("strict_weakened", False)
            summary_raw = str(e.get("summary", ""))
            if len(summary_raw) > 120:
                summary_raw = summary_raw[:117] + "..."
            summary = html.escape(summary_raw)
            parts.append("<tr>")
            parts.append(f"<td>{ts_str}</td>")
            parts.append(f"<td>{_badge(drift)}</td>")
            parts.append(f"<td>{missing}</td>")
            parts.append(f"<td>{extra}</td>")
            parts.append(f"<td>{_badge(strict)}</td>")
            parts.append(f"<td>{summary}</td>")
            parts.append("</tr>")
        parts.append("</tbody></table>")
    else:
        parts.append('<div class="empty">No drift entries in window.</div>')

    parts.append("</body></html>\n")
    return "\n".join(parts)


class DriftHtmlRenderer:
    """Render S16.9 drift history as a static HTML5 report page."""

    def __init__(
        self,
        history_store: DriftHistoryStore,
        clock: Callable[[], float],
        file_writer: FileWriter | None = None,
    ) -> None:
        self._history_store = history_store
        self._clock = clock
        self._file_writer: FileWriter = file_writer or _default_file_writer

    def render(
        self,
        report_path: str,
        window_seconds: int = 604800,
        limit: int = 500,
    ) -> RenderResult:
        """Read history, render HTML, write file. Never raises."""
        now = self._clock()
        try:
            since_ts = now - window_seconds
            entries = self._history_store.read_since(since_ts)
            # most-recent first, cap to limit
            entries.sort(key=lambda e: e.get("ts", 0), reverse=True)
            if limit > 0:
                entries = entries[:limit]
            body = _render_html(entries, window_seconds, now)
            self._file_writer(report_path, body)
            return RenderResult(
                success=True,
                report_path=report_path,
                rendered_at=now,
                entries_rendered=len(entries),
                byte_size=len(body.encode("utf-8")),
            )
        except Exception as exc:  # noqa: BLE001
            return RenderResult(
                success=False,
                report_path=report_path,
                rendered_at=now,
                entries_rendered=0,
                error=str(exc),
            )
