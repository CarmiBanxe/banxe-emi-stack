"""
services/fatca_crs/hmrc_models.py
HMRC FATCA/CRS annual reporting models (IL-HMR-01).
I-01: all amounts as Decimal strings.
XML schema: OECD CRS XML Schema v2.0 / HMRC FATCA Form 8966 equivalent.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, field_validator


class AccountHolder(BaseModel):
    account_id: str
    customer_id: str
    name: str
    country_of_residence: str
    tin: str  # masked in logs
    us_person: bool = False
    model_config = {"frozen": True}

    def masked_tin(self) -> str:
        return f"****{self.tin[-4:]}" if len(self.tin) >= 4 else "****"


class ReportableAccount(BaseModel):
    account_id: str
    account_holder: AccountHolder
    balance: str  # Decimal as string (I-01)
    currency: str = "GBP"
    account_type: str = "Depository"
    reportable_jurisdiction: str
    tax_year: int
    model_config = {"frozen": True}

    @field_validator("balance")
    @classmethod
    def validate_balance(cls, v: str) -> str:
        try:
            Decimal(v)
        except Exception as exc:
            raise ValueError(f"Value {v!r} is not a valid Decimal string (I-01)") from exc
        return v


class FinancialInstitution(BaseModel):
    fi_id: str
    name: str
    country: str = "GB"
    giin: str = "BANXE-EMI-GIIN"  # Global Intermediary Identification Number
    model_config = {"frozen": True}


class HMRCReport(BaseModel):
    report_id: str
    tax_year: int
    fi: FinancialInstitution
    fatca_accounts: list[ReportableAccount]  # US-reportable
    crs_accounts: list[ReportableAccount]  # Multi-jurisdiction CRS
    generated_at: str
    status: str = "DRAFT"
    model_config = {"frozen": True}

    @property
    def total_accounts(self) -> int:
        return len(self.fatca_accounts) + len(self.crs_accounts)


class HMRCValidationError(BaseModel):
    field: str
    message: str
    model_config = {"frozen": True}


class HMRCValidationResult(BaseModel):
    report_id: str
    valid: bool
    errors: list[HMRCValidationError] = []
    model_config = {"frozen": True}


class HMRCSubmissionResult(BaseModel):
    report_id: str
    submitted: bool
    hmrc_reference: str | None = None
    submitted_at: str | None = None
    error: str | None = None
    model_config = {"frozen": True}
