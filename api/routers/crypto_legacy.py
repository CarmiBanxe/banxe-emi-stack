"""
api/routers/crypto_legacy.py — Wave E legacy crypto endpoints (ADR-031, Phase 5 Step 1)

Prefix: /v1/crypto-legacy (set in api/main.py)

GET  /health                                  — aggregate adapter health
GET  /balance/{blockchain}/{wallet_id}        — REWRITE-7: get_balance
POST /wallet-address                          — REWRITE-7: create_wallet_address
POST /tx                                      — REWRITE-8: create_tx (idempotent on tx_id)
GET  /fee-estimate/{blockchain}               — REWRITE-8: get_fee_estimate
POST /broadcast                               — REWRITE-9: broadcast_tx
GET  /block/{blockchain}/{block_hash}         — REWRITE-9: get_block
GET  /rpc/fee-estimate/{blockchain}/{priority} — REWRITE-9: estimate_fee

All amounts returned as strings (I-05: DecimalString). No float anywhere (I-01).
In-memory scaffold only — no network calls, no DB.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_crypto_application_service
from services.ledger.crypto_application_service import CryptoApplicationService
from services.ledger.crypto_ledger_port import FeePriority, SupportedBlockchain

router = APIRouter(tags=["Crypto Legacy (Wave E)"])


# ── Response models ───────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    wallet: bool
    processing: bool
    rpc: bool


class BalanceResponse(BaseModel):
    wallet_id: str
    blockchain: str
    confirmed_balance: str
    unconfirmed_balance: str
    currency: str
    as_of: str


class WalletAddressRequest(BaseModel):
    customer_id: str
    blockchain: SupportedBlockchain


class WalletAddressResponse(BaseModel):
    wallet_id: str
    customer_id: str
    blockchain: str
    address: str
    created_at: str


class CreateTxRequest(BaseModel):
    tx_id: str
    from_wallet_id: str
    to_address: str
    blockchain: SupportedBlockchain
    amount: str  # DecimalString — I-05
    currency: str
    fee_level: FeePriority
    customer_id: str


class TxResultResponse(BaseModel):
    tx_id: str
    tx_hash: str | None
    blockchain: str
    amount: str
    fee: str
    currency: str
    status: str
    from_wallet_id: str
    to_address: str
    created_at: str
    confirmed_at: str | None


class FeeEstimateResponse(BaseModel):
    blockchain: str
    fee: str
    currency: str
    priority: str
    estimated_confirmation_blocks: int


class BroadcastRequest(BaseModel):
    signed_tx: str
    blockchain: SupportedBlockchain


class BroadcastResponse(BaseModel):
    tx_hash: str


class BlockResponse(BaseModel):
    block_hash: str
    block_number: int
    blockchain: str
    timestamp: str
    tx_count: int


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/health", response_model=HealthResponse)
async def crypto_legacy_health(
    svc: CryptoApplicationService = Depends(get_crypto_application_service),
) -> HealthResponse:
    result = svc.health()
    return HealthResponse(**result)


@router.get("/balance/{blockchain}/{wallet_id}", response_model=BalanceResponse)
async def get_balance(
    blockchain: SupportedBlockchain,
    wallet_id: str,
    svc: CryptoApplicationService = Depends(get_crypto_application_service),
) -> BalanceResponse:
    bal = svc.get_balance(wallet_id, blockchain)
    return BalanceResponse(
        wallet_id=bal.wallet_id,
        blockchain=bal.blockchain,
        confirmed_balance=str(bal.confirmed_balance),
        unconfirmed_balance=str(bal.unconfirmed_balance),
        currency=bal.currency,
        as_of=bal.as_of.isoformat(),
    )


@router.post("/wallet-address", response_model=WalletAddressResponse)
async def create_wallet_address(
    body: WalletAddressRequest,
    svc: CryptoApplicationService = Depends(get_crypto_application_service),
) -> WalletAddressResponse:
    addr = svc.create_wallet_address(body.customer_id, body.blockchain)
    return WalletAddressResponse(
        wallet_id=addr.wallet_id,
        customer_id=addr.customer_id,
        blockchain=addr.blockchain,
        address=addr.address,
        created_at=addr.created_at.isoformat(),
    )


@router.post("/tx", response_model=TxResultResponse)
async def create_tx(
    body: CreateTxRequest,
    svc: CryptoApplicationService = Depends(get_crypto_application_service),
) -> TxResultResponse:
    from services.ledger.crypto_ledger_port import CryptoTransactionRequest

    req = CryptoTransactionRequest(
        tx_id=body.tx_id,
        from_wallet_id=body.from_wallet_id,
        to_address=body.to_address,
        blockchain=body.blockchain,
        amount=Decimal(body.amount),
        currency=body.currency,
        fee_level=body.fee_level,
        customer_id=body.customer_id,
    )
    result = svc.create_tx(req)
    return TxResultResponse(
        tx_id=result.tx_id,
        tx_hash=result.tx_hash,
        blockchain=result.blockchain,
        amount=str(result.amount),
        fee=str(result.fee),
        currency=result.currency,
        status=result.status,
        from_wallet_id=result.from_wallet_id,
        to_address=result.to_address,
        created_at=result.created_at.isoformat(),
        confirmed_at=result.confirmed_at.isoformat() if result.confirmed_at else None,
    )


@router.get("/fee-estimate/{blockchain}", response_model=FeeEstimateResponse)
async def get_fee_estimate(
    blockchain: SupportedBlockchain,
    amount: str = "1.0",
    svc: CryptoApplicationService = Depends(get_crypto_application_service),
) -> FeeEstimateResponse:
    est = svc.get_fee_estimate(blockchain, Decimal(amount))
    return FeeEstimateResponse(
        blockchain=est.blockchain,
        fee=str(est.fee),
        currency=est.currency,
        priority=est.priority,
        estimated_confirmation_blocks=est.estimated_confirmation_blocks,
    )


@router.post("/broadcast", response_model=BroadcastResponse)
async def broadcast_tx(
    body: BroadcastRequest,
    svc: CryptoApplicationService = Depends(get_crypto_application_service),
) -> BroadcastResponse:
    tx_hash = svc.broadcast_tx(body.signed_tx, body.blockchain)
    return BroadcastResponse(tx_hash=tx_hash)


@router.get("/block/{blockchain}/{block_hash}", response_model=BlockResponse)
async def get_block(
    blockchain: SupportedBlockchain,
    block_hash: str,
    svc: CryptoApplicationService = Depends(get_crypto_application_service),
) -> BlockResponse:
    blk = svc.get_block(block_hash, blockchain)
    return BlockResponse(
        block_hash=blk.block_hash,
        block_number=blk.block_number,
        blockchain=blk.blockchain,
        timestamp=blk.timestamp.isoformat(),
        tx_count=blk.tx_count,
    )


@router.get("/rpc/fee-estimate/{blockchain}/{priority}", response_model=FeeEstimateResponse)
async def rpc_estimate_fee(
    blockchain: SupportedBlockchain,
    priority: FeePriority,
    svc: CryptoApplicationService = Depends(get_crypto_application_service),
) -> FeeEstimateResponse:
    est = svc.estimate_fee(blockchain, priority)
    return FeeEstimateResponse(
        blockchain=est.blockchain,
        fee=str(est.fee),
        currency=est.currency,
        priority=est.priority,
        estimated_confirmation_blocks=est.estimated_confirmation_blocks,
    )
