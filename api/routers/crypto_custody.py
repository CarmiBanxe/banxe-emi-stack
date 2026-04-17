"""
api/routers/crypto_custody.py — Crypto & Digital Assets Custody REST endpoints
IL-CDC-01 | Phase 35 | banxe-emi-stack
10 endpoints under /v1/crypto/
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from services.crypto_custody.custody_reconciler import CustodyReconciler
from services.crypto_custody.fee_calculator import FeeCalculator
from services.crypto_custody.models import AssetType, NetworkType
from services.crypto_custody.transfer_engine import TransferEngine
from services.crypto_custody.travel_rule_engine import TravelRuleEngine
from services.crypto_custody.wallet_manager import WalletManager

router = APIRouter(tags=["crypto_custody"])


@lru_cache(maxsize=1)
def _wallet_manager() -> WalletManager:
    return WalletManager()


@lru_cache(maxsize=1)
def _transfer_engine() -> TransferEngine:
    return TransferEngine()


@lru_cache(maxsize=1)
def _travel_rule() -> TravelRuleEngine:
    return TravelRuleEngine()


@lru_cache(maxsize=1)
def _reconciler() -> CustodyReconciler:
    return CustodyReconciler()


@lru_cache(maxsize=1)
def _fee_calc() -> FeeCalculator:
    return FeeCalculator()


def _wm_dep() -> WalletManager:
    return _wallet_manager()


def _te_dep() -> TransferEngine:
    return _transfer_engine()


def _tr_dep() -> TravelRuleEngine:
    return _travel_rule()


def _rc_dep() -> CustodyReconciler:
    return _reconciler()


# ── POST /v1/crypto/wallets ───────────────────────────────────────────────────


@router.post("/v1/crypto/wallets", status_code=status.HTTP_201_CREATED)
def create_wallet(
    body: Annotated[dict[str, Any], Body()],
    wm: Annotated[WalletManager, Depends(_wm_dep)],
) -> dict[str, Any]:
    try:
        asset_type = AssetType(body["asset_type"])
        network = NetworkType(body.get("network", "MAINNET"))
        wallet = wm.create_wallet(
            owner_id=body["owner_id"],
            asset_type=asset_type,
            wallet_type=body.get("wallet_type", "HOT"),
            network=network,
        )
        return {
            "id": wallet.id,
            "asset_type": wallet.asset_type.value,
            "status": wallet.status.value,
            "address": wallet.address,
            "balance": str(wallet.balance),
            "network": wallet.network.value,
            "owner_id": wallet.owner_id,
        }
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/crypto/wallets ────────────────────────────────────────────────────


@router.get("/v1/crypto/wallets")
def list_wallets(
    owner_id: str,
    wm: Annotated[WalletManager, Depends(_wm_dep)],
) -> dict[str, Any]:
    wallets = wm.list_wallets(owner_id)
    return {
        "wallets": [
            {
                "id": w.id,
                "asset_type": w.asset_type.value,
                "status": w.status.value,
                "address": w.address,
                "balance": str(w.balance),
                "network": w.network.value,
            }
            for w in wallets
        ]
    }


# ── GET /v1/crypto/wallets/{wallet_id} ───────────────────────────────────────


@router.get("/v1/crypto/wallets/{wallet_id}")
def get_wallet(
    wallet_id: str,
    wm: Annotated[WalletManager, Depends(_wm_dep)],
) -> dict[str, Any]:
    store = wm._wallets  # type: ignore[attr-defined]
    wallet = store.get_wallet(wallet_id)
    if wallet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found")
    return {
        "id": wallet.id,
        "asset_type": wallet.asset_type.value,
        "status": wallet.status.value,
        "address": wallet.address,
        "balance": str(wallet.balance),
        "network": wallet.network.value,
        "owner_id": wallet.owner_id,
    }


# ── GET /v1/crypto/wallets/{wallet_id}/balance ────────────────────────────────


@router.get("/v1/crypto/wallets/{wallet_id}/balance")
def get_balance(
    wallet_id: str,
    wm: Annotated[WalletManager, Depends(_wm_dep)],
) -> dict[str, Any]:
    try:
        balance = wm.get_balance(wallet_id)
        return {"wallet_id": wallet_id, "balance": str(balance)}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── POST /v1/crypto/wallets/{wallet_id}/archive ───────────────────────────────


@router.post("/v1/crypto/wallets/{wallet_id}/archive")
def archive_wallet(
    wallet_id: str,
    wm: Annotated[WalletManager, Depends(_wm_dep)],
) -> dict[str, Any]:
    try:
        proposal = wm.archive_wallet(wallet_id)
        return {
            "hitl_required": True,
            "action": proposal.action,
            "resource_id": proposal.resource_id,
            "requires_approval_from": proposal.requires_approval_from,
            "reason": proposal.reason,
            "autonomy_level": proposal.autonomy_level,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── POST /v1/crypto/transfers ─────────────────────────────────────────────────


@router.post("/v1/crypto/transfers", status_code=status.HTTP_201_CREATED)
def initiate_transfer(
    body: Annotated[dict[str, Any], Body()],
    te: Annotated[TransferEngine, Depends(_te_dep)],
) -> dict[str, Any]:
    try:
        amount = Decimal(str(body["amount"]))
        asset_type = AssetType(body["asset_type"])
        transfer = te.initiate_transfer(
            from_wallet_id=body["from_wallet_id"],
            to_address=body["to_address"],
            amount=amount,
            asset_type=asset_type,
        )
        return {
            "id": transfer.id,
            "from_wallet_id": transfer.from_wallet_id,
            "to_address": transfer.to_address,
            "amount": str(transfer.amount),
            "asset_type": transfer.asset_type.value,
            "status": transfer.status.value,
            "travel_rule_required": transfer.travel_rule_required,
        }
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/crypto/transfers/{transfer_id} ────────────────────────────────────


@router.get("/v1/crypto/transfers/{transfer_id}")
def get_transfer(
    transfer_id: str,
    te: Annotated[TransferEngine, Depends(_te_dep)],
) -> dict[str, Any]:
    transfer = te._transfers.get_transfer(transfer_id)  # type: ignore[attr-defined]
    if transfer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer not found")
    return {
        "id": transfer.id,
        "from_wallet_id": transfer.from_wallet_id,
        "to_address": transfer.to_address,
        "amount": str(transfer.amount),
        "status": transfer.status.value,
        "travel_rule_required": transfer.travel_rule_required,
        "txhash": transfer.txhash,
    }


# ── POST /v1/crypto/transfers/{transfer_id}/execute ───────────────────────────


@router.post("/v1/crypto/transfers/{transfer_id}/execute")
def execute_transfer(
    transfer_id: str,
    te: Annotated[TransferEngine, Depends(_te_dep)],
) -> dict[str, Any]:
    try:
        result = te.execute_transfer(transfer_id)
        from services.crypto_custody.crypto_agent import HITLProposal  # noqa: PLC0415

        if isinstance(result, HITLProposal):
            return {
                "hitl_required": True,
                "action": result.action,
                "resource_id": result.resource_id,
                "requires_approval_from": result.requires_approval_from,
                "reason": result.reason,
                "autonomy_level": result.autonomy_level,
            }
        return {
            "id": result.id,
            "status": result.status.value,
            "amount": str(result.amount),
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── POST /v1/crypto/transfers/{transfer_id}/confirm ──────────────────────────


@router.post("/v1/crypto/transfers/{transfer_id}/confirm")
def confirm_transfer(
    transfer_id: str,
    body: Annotated[dict[str, Any], Body()],
    te: Annotated[TransferEngine, Depends(_te_dep)],
) -> dict[str, Any]:
    try:
        transfer = te.confirm_on_chain(transfer_id, txhash=body["txhash"])
        return {
            "id": transfer.id,
            "status": transfer.status.value,
            "txhash": transfer.txhash,
        }
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── POST /v1/crypto/travel-rule/check ────────────────────────────────────────


@router.post("/v1/crypto/travel-rule/check")
def travel_rule_check(
    body: Annotated[dict[str, Any], Body()],
    tr: Annotated[TravelRuleEngine, Depends(_tr_dep)],
) -> dict[str, Any]:
    try:
        amount_eur = Decimal(str(body["amount_eur"]))
        jurisdiction = body["jurisdiction"]
        requires = tr.requires_travel_rule(amount_eur)
        screening = tr.screen_jurisdiction(jurisdiction)
        return {
            "jurisdiction": jurisdiction,
            "amount_eur": str(amount_eur),
            "travel_rule_required": requires,
            "jurisdiction_screening": screening,
        }
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
