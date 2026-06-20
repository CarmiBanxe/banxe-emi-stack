"""api/models/account_sot.py — Advisory account/balance SoT (MIG-M2.2) | banxe-emi-stack.

The **advisory account-metadata Source-of-Truth**: descriptive account metadata, virtual-account
descriptors, and intermediary-bank descriptors. **Balance-free by design** — it does NOT hold or
return live balances and **does NOT call the Midaz LedgerPort** (``api/models/ledger.py`` +
``services/ledger`` remain the live balance SoT, ADR-013). Payments (MIG-M2.1) will be a
**projection-consumer** of this SoT, never a second balance store (MIG-M1.3).

Consumes the **accounts-connector** contract baseline pinned in MIG-M2.0/M2.7 (``@banxe/*`` from
``banxe-shared-libs``) at the **gRPC/proto contract level** (language-agnostic; not an npm import).
Advisory / read-only / sandbox-mock-safe. Numerics: integer meta / DecimalString only (I-01) — no
balances, no float.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

SANDBOX_SOURCE = "sandbox-mock"


class AccountAdvisoryMetadata(BaseModel):
    """Descriptive advisory account metadata (read-only; NOT a live account/balance)."""

    account_type: str
    ledger_nature: str
    account_status: str
    supported_assets: list[str]
    capabilities: list[str]
    source: str


class VirtualAccountDescriptor(BaseModel):
    """Descriptive virtual-account record (balance-free; no live amount)."""

    virtual_account_id: str
    parent_account_ref: str
    asset: str
    status: str
    source: str


class IntermediaryBankDescriptor(BaseModel):
    """Descriptive intermediary-bank routing record (reference-only)."""

    name: str
    bic: str
    country: str
    role: str
    source: str


class AccountSoTMetadataResponse(BaseModel):
    """Advisory account-metadata SoT response (balance-free)."""

    accounts: list[AccountAdvisoryMetadata]
    source: str
    disclaimer: str


class VirtualAccountListResponse(BaseModel):
    by_virtual_account: list[VirtualAccountDescriptor]
    total: int
    source: str


class IntermediaryListResponse(BaseModel):
    intermediaries: list[IntermediaryBankDescriptor]
    total: int
    source: str


_DISCLAIMER = (
    "Advisory account-metadata SoT — descriptive only. NOT a balance/ledger surface; "
    "balances are owned by the Midaz LedgerPort (live), never returned here."
)

# Config-as-data sandbox descriptors (balance-free; no Midaz call).
_ACCOUNTS: tuple[dict[str, object], ...] = (
    {
        "account_type": "INTERNAL",
        "ledger_nature": "ACTIVE",
        "account_status": "ACTIVE",
        "supported_assets": ["EUR", "GBP", "USD", "CHF", "BTC", "ETH", "USDC"],
        "capabilities": ["fiat", "crypto", "self_custodial"],
    },
    {
        "account_type": "EXTERNAL",
        "ledger_nature": "PASSIVE",
        "account_status": "ACTIVE",
        "supported_assets": ["EUR", "GBP", "USD", "CHF"],
        "capabilities": ["fiat"],
    },
    {
        "account_type": "SYSTEM",
        "ledger_nature": "ACTIVE",
        "account_status": "ACTIVE",
        "supported_assets": [],
        "capabilities": ["internal"],
    },
)
_VIRTUAL_ACCOUNTS: tuple[dict[str, str], ...] = (
    {
        "virtual_account_id": "VA-EUR-0001",
        "parent_account_ref": "INTERNAL",
        "asset": "EUR",
        "status": "ACTIVE",
    },
    {
        "virtual_account_id": "VA-GBP-0001",
        "parent_account_ref": "INTERNAL",
        "asset": "GBP",
        "status": "ACTIVE",
    },
)
_INTERMEDIARIES: tuple[dict[str, str], ...] = (
    {"name": "Intermediary Bank A", "bic": "INTBGB2L", "country": "GB", "role": "correspondent"},
    {"name": "Intermediary Bank B", "bic": "INTBDEFF", "country": "DE", "role": "correspondent"},
)


class AccountSoTPort(ABC):
    """Read-only advisory account-metadata SoT contract (balance-free; Midaz LedgerPort NOT called)."""

    @abstractmethod
    def list_account_metadata(self) -> list[AccountAdvisoryMetadata]: ...

    @abstractmethod
    def list_virtual_accounts(self) -> list[VirtualAccountDescriptor]: ...

    @abstractmethod
    def list_intermediaries(self) -> list[IntermediaryBankDescriptor]: ...


class SandboxAccountSoT(AccountSoTPort):
    """Sandbox config-as-data provider (mock-safe; no Midaz, no balances)."""

    def list_account_metadata(self) -> list[AccountAdvisoryMetadata]:
        return [AccountAdvisoryMetadata(source=SANDBOX_SOURCE, **a) for a in _ACCOUNTS]  # type: ignore[arg-type]

    def list_virtual_accounts(self) -> list[VirtualAccountDescriptor]:
        return [VirtualAccountDescriptor(source=SANDBOX_SOURCE, **v) for v in _VIRTUAL_ACCOUNTS]

    def list_intermediaries(self) -> list[IntermediaryBankDescriptor]:
        return [IntermediaryBankDescriptor(source=SANDBOX_SOURCE, **i) for i in _INTERMEDIARIES]


def account_sot_metadata_response() -> AccountSoTMetadataResponse:
    sot = SandboxAccountSoT()
    return AccountSoTMetadataResponse(
        accounts=sot.list_account_metadata(),
        source=SANDBOX_SOURCE,
        disclaimer=_DISCLAIMER,
    )


def virtual_account_list_response() -> VirtualAccountListResponse:
    items = SandboxAccountSoT().list_virtual_accounts()
    return VirtualAccountListResponse(
        by_virtual_account=items, total=len(items), source=SANDBOX_SOURCE
    )


def intermediary_list_response() -> IntermediaryListResponse:
    items = SandboxAccountSoT().list_intermediaries()
    return IntermediaryListResponse(intermediaries=items, total=len(items), source=SANDBOX_SOURCE)
