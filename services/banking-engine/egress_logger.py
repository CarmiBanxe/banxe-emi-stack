# Enforces API Contract egress logging: every outbound call carries X-Request-ID
# and is written append-only to the sandbox egress log.
"""
Egress logger for Banking Engine sandbox.

Attaches X-Request-ID to every outbound HTTP call and appends a structured
log line to the sandbox egress log file.  No secrets, no PII are logged —
only method, URL scheme+host+path (query params stripped), status code, and
the request ID.
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import uuid

_EGRESS_LOG_PATH: Path = Path(os.getenv("BANKING_EGRESS_LOG", "logs/banking-engine-egress.jsonl"))

_logger = logging.getLogger(__name__)


def _sanitise_url(url: str) -> str:
    """Strip query params and fragment; keep scheme+netloc+path only."""
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}{p.path}"


def generate_request_id() -> str:
    return str(uuid.uuid4())


def log_egress(
    *,
    request_id: str,
    method: str,
    url: str,
    status_code: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append one egress record to the sandbox log file."""
    _EGRESS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    record: dict[str, Any] = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "request_id": request_id,
        "method": method.upper(),
        "url": _sanitise_url(url),
        "status_code": status_code,
        **(extra or {}),
    }

    with _EGRESS_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")

    _logger.debug("egress logged request_id=%s url=%s", request_id, record["url"])


class EgressSession:
    """
    Thin wrapper that injects X-Request-ID into outbound call kwargs and
    logs the result via log_egress.

    Usage (sync, with httpx or requests)::

        session = EgressSession()
        rid, headers = session.prepare_headers()
        resp = httpx.get(url, headers=headers)
        session.log(rid, "GET", url, resp.status_code)
    """

    def prepare_headers(self, request_id: str | None = None) -> tuple[str, dict[str, str]]:
        rid = request_id or generate_request_id()
        return rid, {"X-Request-ID": rid}

    def log(
        self,
        request_id: str,
        method: str,
        url: str,
        status_code: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        log_egress(
            request_id=request_id,
            method=method,
            url=url,
            status_code=status_code,
            extra=extra,
        )
