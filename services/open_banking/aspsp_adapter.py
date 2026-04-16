"""
services/open_banking/aspsp_adapter.py
IL-OBK-01 | Phase 15

Adapters for ASPSP API standards:
- Berlin Group NextGenPSD2 3.1 (EU continental banks)
- UK OBIE 3.1 (UK Open Banking)
"""

from __future__ import annotations

from services.open_banking.models import (
    AccountAccessType,
    ASPSPRegistryPort,
    ASPSPStandard,
    ConsentType,
    PaymentInitiation,
)


class BerlinGroupAdapter:
    """NextGenPSD2 3.1 format for Berlin Group standard ASPSPs."""

    def build_consent_request(
        self,
        consent_type: ConsentType,
        permissions: list[AccountAccessType],
    ) -> dict:
        """Build a Berlin Group NextGenPSD2 consent request body."""
        access: dict = {}
        if AccountAccessType.ACCOUNTS in permissions:
            access["accounts"] = [{"iban": ""}]
        if AccountAccessType.BALANCES in permissions:
            access["balances"] = [{"iban": ""}]
        if AccountAccessType.TRANSACTIONS in permissions:
            access["transactions"] = [{"iban": ""}]
        return {
            "access": access,
            "combinedServiceIndicator": False,
            "frequencyPerDay": 4,
            "recurringIndicator": True,
            "validUntil": None,
        }

    def build_payment_request(self, payment: PaymentInitiation) -> dict:
        """Build a Berlin Group NextGenPSD2 payment initiation request body."""
        body: dict = {
            "endToEndIdentification": payment.end_to_end_id,
            "instructedAmount": {
                "currency": payment.currency,
                "amount": str(payment.amount),
            },
            "creditorAccount": {"iban": payment.creditor_iban},
            "creditorName": payment.creditor_name,
            "remittanceInformationUnstructured": payment.reference,
        }
        if payment.debtor_iban:
            body["debtorAccount"] = {"iban": payment.debtor_iban}
        return body

    def parse_payment_response(self, response: dict) -> str:
        """Extract aspsp_payment_id from Berlin Group response."""
        payment_id = response.get("paymentId") or response.get("transactionStatus", "")
        if not payment_id:
            raise ValueError("No paymentId in Berlin Group response")
        return str(payment_id)


class UKOBIEAdapter:
    """UK OBIE 3.1 format for UK Open Banking standard ASPSPs."""

    def build_consent_request(
        self,
        consent_type: ConsentType,
        permissions: list[AccountAccessType],
    ) -> dict:
        """Build a UK OBIE consent request body."""
        obie_permissions = []
        permission_map = {
            AccountAccessType.ACCOUNTS: ["ReadAccountsBasic", "ReadAccountsDetail"],
            AccountAccessType.BALANCES: ["ReadBalances"],
            AccountAccessType.TRANSACTIONS: ["ReadTransactionsBasic", "ReadTransactionsDetail"],
            AccountAccessType.BENEFICIARIES: ["ReadBeneficiariesBasic", "ReadBeneficiariesDetail"],
        }
        for perm in permissions:
            obie_permissions.extend(permission_map.get(perm, []))

        return {
            "Data": {
                "Permissions": obie_permissions,
                "ExpirationDateTime": None,
                "TransactionFromDateTime": None,
                "TransactionToDateTime": None,
            },
            "Risk": {},
        }

    def build_payment_request(self, payment: PaymentInitiation) -> dict:
        """Build a UK OBIE domestic payment initiation request body."""
        body: dict = {
            "Data": {
                "ConsentId": payment.consent_id,
                "Initiation": {
                    "InstructionIdentification": payment.id,
                    "EndToEndIdentification": payment.end_to_end_id,
                    "InstructedAmount": {
                        "Amount": str(payment.amount),
                        "Currency": payment.currency,
                    },
                    "CreditorAccount": {
                        "SchemeName": "UK.OBIE.IBAN",
                        "Identification": payment.creditor_iban,
                        "Name": payment.creditor_name,
                    },
                    "RemittanceInformation": {
                        "Unstructured": payment.reference,
                    },
                },
            },
            "Risk": {},
        }
        if payment.debtor_iban:
            body["Data"]["Initiation"]["DebtorAccount"] = {
                "SchemeName": "UK.OBIE.IBAN",
                "Identification": payment.debtor_iban,
            }
        return body

    def parse_payment_response(self, response: dict) -> str:
        """Extract aspsp_payment_id from UK OBIE response."""
        data = response.get("Data", {})
        payment_id = data.get("DomesticPaymentId") or data.get("ConsentId", "")
        if not payment_id:
            raise ValueError("No DomesticPaymentId in UK OBIE response")
        return str(payment_id)


class ASPSPAdapter:
    """Unified adapter — delegates to Berlin Group or UK OBIE based on standard."""

    def __init__(self, registry: ASPSPRegistryPort) -> None:
        self._registry = registry
        self._berlin = BerlinGroupAdapter()
        self._obie = UKOBIEAdapter()

    async def build_consent_request(
        self,
        aspsp_id: str,
        consent_type: ConsentType,
        permissions: list[AccountAccessType],
    ) -> dict:
        """Build a consent request body for the given ASPSP standard."""
        aspsp = await self._registry.get(aspsp_id)
        if aspsp is None:
            raise ValueError(f"ASPSP not found: {aspsp_id}")
        if aspsp.standard == ASPSPStandard.BERLIN_GROUP:
            return self._berlin.build_consent_request(consent_type, permissions)
        return self._obie.build_consent_request(consent_type, permissions)

    async def build_payment_request(self, payment: PaymentInitiation) -> dict:
        """Build a payment request body for the ASPSP that owns this payment."""
        aspsp = await self._registry.get(payment.aspsp_id)
        if aspsp is None:
            raise ValueError(f"ASPSP not found: {payment.aspsp_id}")
        if aspsp.standard == ASPSPStandard.BERLIN_GROUP:
            return self._berlin.build_payment_request(payment)
        return self._obie.build_payment_request(payment)

    async def parse_payment_response(
        self,
        aspsp_id: str,
        response: dict,
    ) -> str:
        """Parse payment response and return aspsp_payment_id."""
        aspsp = await self._registry.get(aspsp_id)
        if aspsp is None:
            raise ValueError(f"ASPSP not found: {aspsp_id}")
        if aspsp.standard == ASPSPStandard.BERLIN_GROUP:
            return self._berlin.parse_payment_response(response)
        return self._obie.parse_payment_response(response)
