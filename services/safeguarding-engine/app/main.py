"""Safeguarding Engine — FastAPI application factory."""
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from prometheus_client import make_asgi_app

from app.config import get_settings
from app.api.router import api_router
from app.dependencies import init_db, close_db, init_redis, close_redis

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    settings = get_settings()
    logger.info("safeguarding-engine.startup", port=settings.port)
    await init_db()
    await init_redis()
    yield
    await close_redis()
    await close_db()
    logger.info("safeguarding-engine.shutdown")


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title="Banxe Safeguarding Engine",
        description="FCA CASS 15 safeguarding engine — segregated accounts, daily reconciliation, breach reporting",
        version=settings.service_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Mount Prometheus metrics
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # Include API router
    app.include_router(api_router, prefix="/api/v1")

    return app


# Module-level app instance for uvicorn
app = create_app()

if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
