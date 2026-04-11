"""
services/agent_routing/playbook_engine.py — Playbook Engine
IL-ARL-01 | banxe-emi-stack

Loads YAML playbooks from config/playbooks/ and matches incoming events
to a playbook by (product, jurisdiction). Evaluates tier assignment rules
against the risk_context.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_PLAYBOOKS_DIR = Path(__file__).parent.parent.parent / "config" / "playbooks"

# Supported comparison operators in tier rule conditions
_OP_RE = re.compile(r"^(?P<key>\w+)\s*(?P<op>>=|<=|>|<|=|in)\s*(?P<val>.+)$")


class PlaybookNotFoundError(Exception):
    """Raised when no playbook matches the given product/jurisdiction."""


class PlaybookParseError(Exception):
    """Raised when a playbook YAML cannot be parsed or is missing required fields."""


class PlaybookEngine:
    """Loads and evaluates routing playbooks.

    Usage::

        engine = PlaybookEngine()
        tier, playbook_id = engine.assign_tier(
            product="sepa_retail_transfer",
            jurisdiction="EU",
            risk_context={"known_beneficiary": True, "amount_eur": 500, ...},
        )
    """

    def __init__(self, playbooks_dir: Path | None = None) -> None:
        self._dir = playbooks_dir or _PLAYBOOKS_DIR
        self._playbooks: dict[str, dict] = {}
        self._load_all()

    # ── Loading ───────────────────────────────────────────────────────────────

    def _load_all(self) -> None:
        """Load all YAML playbooks from the playbooks directory."""
        if not self._dir.exists():
            logger.warning("Playbooks directory not found: %s", self._dir)
            return
        for path in sorted(self._dir.glob("*.yaml")):
            try:
                playbook = self._load_one(path)
                self._playbooks[playbook["playbook_id"]] = playbook
                logger.debug("Loaded playbook %s", playbook["playbook_id"])
            except PlaybookParseError as exc:
                logger.error("Failed to load playbook %s: %s", path.name, exc)

    def _load_one(self, path: Path) -> dict:
        """Parse a single playbook YAML and validate required fields."""
        with path.open() as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            raise PlaybookParseError(f"{path.name}: top-level must be a mapping")
        for required in ("playbook_id", "product", "jurisdictions", "tiers"):
            if required not in data:
                raise PlaybookParseError(f"{path.name}: missing required field '{required}'")
        return data

    def reload(self) -> None:
        """Reload all playbooks from disk (for hot-reload in production)."""
        self._playbooks.clear()
        self._load_all()

    # ── Public API ────────────────────────────────────────────────────────────

    def list_playbooks(self) -> list[str]:
        """Return list of loaded playbook IDs."""
        return list(self._playbooks.keys())

    def get_playbook(self, playbook_id: str) -> dict | None:
        """Return a playbook by ID, or None if not found."""
        return self._playbooks.get(playbook_id)

    def find_playbook(self, product: str, jurisdiction: str) -> dict | None:
        """Find the first playbook matching the given product and jurisdiction."""
        for pb in self._playbooks.values():
            if pb["product"] == product:
                juris = pb.get("jurisdictions", [])
                if jurisdiction in juris or "*" in juris:
                    return pb
        return None

    def assign_tier(
        self,
        product: str,
        jurisdiction: str,
        risk_context: dict[str, Any],
    ) -> tuple[int, str]:
        """Determine routing tier for a given product/jurisdiction/risk_context.

        Returns:
            (tier, playbook_id) where tier is 1, 2, or 3.

        Raises:
            PlaybookNotFoundError: if no playbook matches product+jurisdiction.
        """
        playbook = self.find_playbook(product, jurisdiction)
        if playbook is None:
            raise PlaybookNotFoundError(
                f"No playbook found for product={product!r}, jurisdiction={jurisdiction!r}"
            )
        playbook_id: str = playbook["playbook_id"]
        tiers: dict = playbook.get("tiers", {})

        # Evaluate Tier 3 triggers first (highest priority)
        if self._evaluate_tier_triggers(tiers.get("tier3", {}), risk_context):
            return 3, playbook_id

        # Evaluate Tier 2 triggers
        if self._evaluate_tier_triggers(tiers.get("tier2", {}), risk_context):
            return 2, playbook_id

        # Evaluate Tier 1 allowed_if conditions
        tier1_cfg = tiers.get("tier1", {})
        if self._evaluate_tier1_allowed(tier1_cfg, risk_context):
            return 1, playbook_id

        # Default to Tier 2 when no specific tier matched
        return 2, playbook_id

    # ── Condition evaluation ──────────────────────────────────────────────────

    def _evaluate_tier_triggers(self, tier_cfg: dict, ctx: dict[str, Any]) -> bool:
        """Return True if ANY trigger condition matches."""
        triggers = tier_cfg.get("triggers", [])
        if not triggers:
            return False
        return any(self._eval_condition(cond, ctx) for cond in triggers)

    def _evaluate_tier1_allowed(self, tier1_cfg: dict, ctx: dict[str, Any]) -> bool:
        """Return True if ALL allowed_if conditions are satisfied."""
        allowed = tier1_cfg.get("allowed_if", [])
        if not allowed:
            return False
        # Check max_amount if specified
        max_amount = tier1_cfg.get("max_amount_eur")
        if max_amount is not None:
            from decimal import Decimal

            amount = Decimal(str(ctx.get("amount_eur", 0)))
            if amount > Decimal(str(max_amount)):
                return False
        return all(self._eval_condition(cond, ctx) for cond in allowed)

    def _eval_condition(self, condition: str, ctx: dict[str, Any]) -> bool:
        """Evaluate a single condition string against the risk context."""
        condition = condition.strip()
        m = _OP_RE.match(condition)
        if not m:
            logger.warning("Unparseable condition: %r", condition)
            return False
        key = m.group("key")
        op = m.group("op")
        raw_val = m.group("val").strip()
        ctx_val = ctx.get(key)
        if ctx_val is None:
            return False
        return self._compare(ctx_val, op, raw_val)

    @staticmethod
    def _compare(ctx_val: Any, op: str, raw_val: str) -> bool:
        """Compare ctx_val to raw_val using the given operator."""
        # Boolean coercions
        if raw_val.lower() == "true":
            typed_val: Any = True
        elif raw_val.lower() == "false":
            typed_val = False
        elif raw_val.startswith("[") and raw_val.endswith("]"):
            # List: e.g. "[low, medium]" or "[low]"
            items = [i.strip().strip("'\"") for i in raw_val[1:-1].split(",")]
            typed_val = items
        else:
            # Try numeric, fall back to string
            try:
                typed_val = float(raw_val)  # nosemgrep: banxe-float-money
            except ValueError:
                typed_val = raw_val.strip("'\"")

        match op:
            case "=":
                return ctx_val == typed_val
            case ">=":
                return float(ctx_val) >= float(typed_val)  # nosemgrep: banxe-float-money
            case "<=":
                return float(ctx_val) <= float(typed_val)  # nosemgrep: banxe-float-money
            case ">":
                return float(ctx_val) > float(typed_val)  # nosemgrep: banxe-float-money
            case "<":
                return float(ctx_val) < float(typed_val)  # nosemgrep: banxe-float-money
            case "in":
                return ctx_val in typed_val
            case _:
                return False
