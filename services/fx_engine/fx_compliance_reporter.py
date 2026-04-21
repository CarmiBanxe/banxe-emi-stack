"""
services/fx_engine/fx_compliance_reporter.py
FX Compliance Reporter
IL-FXE-01 | Sprint 34 | Phase 48

FCA: PS22/9 (FX transaction reporting), EMIR, MLR 2017 Reg.28
Trust Zone: AMBER

Large FX HITL >= £10k (I-04, I-27). PS22/9 report stub.
SHA-256 audit export. All amounts Decimal (I-22).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
import logging

from services.fx_engine.models import HITLProposal

logger = logging.getLogger(__name__)

LARGE_FX_REPORT_THRESHOLD = Decimal("10000")  # I-04


class FXComplianceReporter:
    """FX compliance reporting and audit trail.

    Large FX report requires HITL (I-04, I-27).
    PS22/9 stub for regulatory activation.
    SHA-256 integrity check on audit exports.
    """

    def __init__(self) -> None:
        """Initialise reporter with empty records."""
        self._reports: list[dict[str, object]] = []
        self._volumes: dict[str, list[Decimal]] = {}

    def report_large_fx(
        self, execution_id: str, amount: Decimal, currency_pair: str, actor: str
    ) -> HITLProposal:
        """Report a large FX transaction (always HITL, I-04, I-27).

        If amount >= £10k → HITLProposal requiring COMPLIANCE_OFFICER approval.

        Args:
            execution_id: FX execution ID.
            amount: Transaction amount (Decimal, I-22).
            currency_pair: e.g. "GBP/EUR".
            actor: Actor submitting the report.

        Returns:
            HITLProposal for COMPLIANCE_OFFICER approval.
        """
        logger.warning(
            "Large FX report execution_id=%s amount=%s %s actor=%s — HITL (I-27)",
            execution_id,
            amount,
            currency_pair,
            actor,
        )
        self._reports.append(
            {
                "execution_id": execution_id,
                "amount": str(amount),
                "currency_pair": currency_pair,
                "actor": actor,
                "reported_at": datetime.now(UTC).isoformat(),
                "status": "pending_hitl",
            }
        )
        return HITLProposal(
            action="LARGE_FX_REPORT",
            quote_id=execution_id,
            requires_approval_from="COMPLIANCE_OFFICER",
            reason=f"Large FX {amount} {currency_pair} >= £10k threshold requires regulatory reporting (I-04)",
            autonomy_level="L4",
        )

    def generate_ps229_report(self, period: str) -> dict[str, object]:
        """Generate PS22/9 FX transaction report stub.

        Stub for regulatory activation — returns report template.

        Args:
            period: Reporting period (e.g. "2026-Q1").

        Returns:
            Dict with PS22/9 report format.
        """
        return {
            "report_type": "PS22/9",
            "period": period,
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "stub",
            "note": "BT-005: PS22/9 live reporting not yet integrated",
            "total_transactions": len(self._reports),
        }

    def get_daily_volume(self, currency_pair: str) -> dict[str, object]:
        """Get daily volume for a currency pair.

        Args:
            currency_pair: e.g. "GBP/EUR".

        Returns:
            Dict with volume as Decimal values (I-22).
        """
        volumes = self._volumes.get(currency_pair, [])
        total = sum(volumes, Decimal("0"))
        return {
            "currency_pair": currency_pair,
            "transaction_count": len(volumes),
            "total_volume": total,
            "date": datetime.now(UTC).date().isoformat(),
        }

    def record_volume(self, currency_pair: str, amount: Decimal) -> None:
        """Record a transaction volume for a currency pair.

        Args:
            currency_pair: e.g. "GBP/EUR".
            amount: Transaction amount (Decimal, I-22).
        """
        if currency_pair not in self._volumes:
            self._volumes[currency_pair] = []
        self._volumes[currency_pair].append(amount)

    def export_fx_audit_trail(self, currency_pair: str) -> dict[str, object]:
        """Export FX audit trail with SHA-256 integrity checksum.

        Args:
            currency_pair: e.g. "GBP/EUR".

        Returns:
            Dict with audit data and SHA-256 checksum.
        """
        export_data = {
            "currency_pair": currency_pair,
            "reports": [
                r for r in self._reports if str(r.get("currency_pair", "")) == currency_pair
            ],
            "volumes": [str(v) for v in self._volumes.get(currency_pair, [])],
            "exported_at": datetime.now(UTC).isoformat(),
        }
        serialised = json.dumps(export_data, sort_keys=True, default=str)
        checksum = hashlib.sha256(serialised.encode()).hexdigest()
        export_data["sha256_checksum"] = checksum
        return export_data

    def get_compliance_summary(self) -> dict[str, object]:
        """Get compliance summary statistics.

        Returns:
            Dict with large_fx_count, total_volume (Decimal), pending_reports.
        """
        pending = sum(1 for r in self._reports if r.get("status") == "pending_hitl")
        all_volumes: list[Decimal] = []
        for vols in self._volumes.values():
            all_volumes.extend(vols)
        total_volume = sum(all_volumes, Decimal("0"))

        return {
            "large_fx_count": len(self._reports),
            "total_volume": total_volume,
            "pending_reports": pending,
        }
