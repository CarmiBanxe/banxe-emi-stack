"""Safeguarding Engine configuration via pydantic-settings."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Service
    service_name: str = "safeguarding-engine"
    service_version: str = "0.1.0"
    debug: bool = False
    host: str = "0.0.0.0"  # nosec B104 — container-internal bind, ingress via reverse proxy
    port: int = 8094

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://banxe:banxe@localhost:5432/banxe_safeguarding"
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Redis
    redis_url: str = "redis://localhost:6379/4"
    redis_ttl: int = 300  # 5 minutes default cache TTL

    # ClickHouse
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_database: str = "banxe_audit"
    clickhouse_user: str = "default"
    clickhouse_password: str = ""

    # Celery
    celery_broker_url: str = "redis://localhost:6379/5"
    celery_result_backend: str = "redis://localhost:6379/5"

    # Integration endpoints
    midaz_gl_url: str = "http://localhost:3000"
    compliance_service_url: str = "http://localhost:8093"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    n8n_webhook_url: str = "http://localhost:5678/webhook/safeguarding"

    # Safeguarding rules
    recon_tolerance_gbp: float = 0.01  # Penny-exact matching
    safeguarding_deadline_hours: int = 24  # T+1 business day
    breach_auto_escalate_hours: int = 24  # Auto FCA notify after 24h
    daily_recon_cron: str = "0 6 * * *"  # 06:00 UTC daily
    position_calc_cron: str = "0 6 * * *"  # 06:00 UTC daily

    # FCA notification
    fca_breach_notify_email: str = ""
    mlro_email: str = ""
    ceo_email: str = ""

    model_config = {"env_prefix": "SAFEGUARD_", "env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
