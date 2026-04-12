"""Main API router aggregating all endpoint modules."""
from fastapi import APIRouter

from app.api.safeguarding import router as safeguarding_router
from app.api.reconciliation import router as reconciliation_router
from app.api.accounts import router as accounts_router
from app.api.breach import router as breach_router
from app.api.health import router as health_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(safeguarding_router, tags=["Safeguarding"])
api_router.include_router(reconciliation_router, tags=["Reconciliation"])
api_router.include_router(accounts_router, tags=["Accounts"])
api_router.include_router(breach_router, tags=["Breaches"])
api_router.include_router(health_router, tags=["Health"])
