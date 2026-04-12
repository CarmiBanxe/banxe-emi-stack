"""
services/transaction_monitor/config.py — Transaction Monitor configuration
IL-RTM-01 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal
import os


class TransactionMonitorConfig:
    """Configuration for the Transaction Monitor service.

    All thresholds and URLs from environment variables.
    """

    # External service URLs
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379")
    jube_url: str = os.environ.get("JUBE_URL", "http://localhost:5001")
    marble_url: str = os.environ.get("MARBLE_URL", "http://localhost:5002")
    clickhouse_url: str = os.environ.get("CLICKHOUSE_URL", "http://localhost:8123")
    kb_api_url: str = os.environ.get("KB_MCP_URL", "http://localhost:8000")
    ml_model_path: str = os.environ.get("ML_MODEL_PATH", "models/isolation_forest_v1.joblib")

    # Score weights (sum = 1.0) — non-monetary floats
    rules_weight: float = float(  # nosemgrep: banxe-float-money — non-monetary weight
        os.environ.get("RULES_WEIGHT", "0.40")
    )
    ml_weight: float = float(  # nosemgrep: banxe-float-money — non-monetary weight
        os.environ.get("ML_WEIGHT", "0.30")
    )
    velocity_weight: float = float(  # nosemgrep: banxe-float-money — non-monetary weight
        os.environ.get("VELOCITY_WEIGHT", "0.30")
    )

    # Velocity thresholds
    velocity_1h_threshold: int = int(os.environ.get("VELOCITY_1H_THRESHOLD", "5"))
    velocity_24h_threshold: int = int(os.environ.get("VELOCITY_24H_THRESHOLD", "15"))
    velocity_7d_threshold: int = int(os.environ.get("VELOCITY_7D_THRESHOLD", "50"))

    # EDD trigger (I-04)
    edd_threshold_individual_gbp: Decimal = Decimal(
        os.environ.get("EDD_THRESHOLD_INDIVIDUAL_GBP", "10000")
    )
    edd_threshold_corporate_gbp: Decimal = Decimal(
        os.environ.get("EDD_THRESHOLD_CORPORATE_GBP", "50000")
    )

    # Hard-block jurisdictions (I-02)
    blocked_jurisdictions: frozenset[str] = frozenset(
        os.environ.get("BLOCKED_JURISDICTIONS", "RU,BY,IR,KP,CU,MM,AF,VE,SY").split(",")
    )

    # FATF greylist (I-03)
    greylist_jurisdictions: frozenset[str] = frozenset(
        os.environ.get(
            "GREYLIST_JURISDICTIONS",
            "AF,AL,BB,BF,CM,CG,HT,JM,JO,ML,MM,MZ,NG,PA,PK,PH,SN,SS,SY,TZ,TT,UG,VN,YE",
        ).split(",")
    )

    # Amount deviation threshold (3x = flag); nosemgrep: banxe-float-money — non-monetary multiplier
    amount_deviation_threshold: float = float(  # nosemgrep: banxe-float-money
        os.environ.get("AMOUNT_DEVIATION_THRESHOLD", "3.0")
    )

    # Round amount detection (structuring)
    round_amount_modulus: int = int(os.environ.get("ROUND_AMOUNT_MODULUS", "1000"))


_config: TransactionMonitorConfig | None = None


def get_config() -> TransactionMonitorConfig:
    global _config
    if _config is None:
        _config = TransactionMonitorConfig()
    return _config
