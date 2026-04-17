"""
services/lending/provisioning_engine.py — IFRS 9 ECL provisioning engine
IL-LCE-01 | Phase 25 | banxe-emi-stack

Computes Expected Credit Loss provisions per IFRS 9 impairment model.
ECL = EAD × PD × LGD — all Decimal arithmetic (I-01).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.lending.models import (
    IFRSStage,
    InMemoryProvisionStore,
    ProvisionRecord,
    ProvisionStorePort,
)

# IFRS 9 parameters per stage
_STAGE_PARAMS: dict[IFRSStage, dict[str, Decimal]] = {
    IFRSStage.STAGE_1: {
        "pd": Decimal("0.01"),
        "lgd": Decimal("0.45"),
    },
    IFRSStage.STAGE_2: {
        "pd": Decimal("0.15"),
        "lgd": Decimal("0.45"),
    },
    IFRSStage.STAGE_3: {
        "pd": Decimal("0.90"),
        "lgd": Decimal("0.65"),
    },
}


class ProvisioningEngine:
    """Computes IFRS 9 Expected Credit Loss provisions for loan exposures."""

    def __init__(self, store: ProvisionStorePort | None = None) -> None:
        self._store = store or InMemoryProvisionStore()

    def compute_ecl(
        self,
        application_id: str,
        ifrs_stage: IFRSStage,
        exposure_at_default: Decimal,
    ) -> ProvisionRecord:
        """Compute ECL provision for a loan exposure.

        ECL = EAD × PD × LGD

        Stage 1 (performing): 12-month ECL, PD=1%, LGD=45%
        Stage 2 (significant deterioration): lifetime ECL, PD=15%, LGD=45%
        Stage 3 (credit-impaired): lifetime ECL, PD=90%, LGD=65%

        Args:
            application_id: Loan application to provision.
            ifrs_stage: IFRS 9 classification stage.
            exposure_at_default: Gross exposure amount (Decimal).

        Returns:
            ProvisionRecord with computed ECL amounts.
        """
        params = _STAGE_PARAMS[ifrs_stage]
        pd = params["pd"]
        lgd = params["lgd"]
        ecl_amount = exposure_at_default * pd * lgd

        record = ProvisionRecord(
            record_id=str(uuid.uuid4()),
            application_id=application_id,
            ifrs_stage=ifrs_stage,
            ecl_amount=ecl_amount,
            probability_of_default=pd,
            exposure_at_default=exposure_at_default,
            computed_at=datetime.now(UTC),
        )
        self._store.save(record)
        return record

    def get_provision_summary(self, application_id: str) -> dict:
        """Return a summary of all provision records for an application.

        Args:
            application_id: Loan application ID.

        Returns:
            dict with total_ecl (Decimal string) and record count.
        """
        records = self._store.list_by_application(application_id)
        total_ecl = sum((r.ecl_amount for r in records), Decimal("0"))
        return {
            "application_id": application_id,
            "total_ecl": str(total_ecl),
            "record_count": len(records),
            "records": [
                {
                    "record_id": r.record_id,
                    "ifrs_stage": r.ifrs_stage.value,
                    "ecl_amount": str(r.ecl_amount),
                    "probability_of_default": str(r.probability_of_default),
                    "exposure_at_default": str(r.exposure_at_default),
                    "computed_at": r.computed_at.isoformat(),
                }
                for r in records
            ],
        }
