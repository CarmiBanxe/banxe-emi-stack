from __future__ import annotations

import pytest

from services.api_gateway.models import InMemoryRequestLogStore
from services.api_gateway.request_logger import RequestLogger


@pytest.fixture()
def logger() -> RequestLogger:
    return RequestLogger()


def test_log_request_returns_request_log(logger: RequestLogger) -> None:
    log = logger.log_request("k1", "GET", "/v1/test", 200, 10, "1.2.3.4")
    assert log is not None
    assert log.key_id == "k1"


def test_log_request_has_log_id(logger: RequestLogger) -> None:
    log = logger.log_request("k1", "POST", "/v1/pay", 201, 50, "1.2.3.4")
    assert log.log_id != ""


def test_log_request_stores_method_and_path(logger: RequestLogger) -> None:
    log = logger.log_request("k1", "DELETE", "/v1/res/1", 204, 5, "1.2.3.4")
    assert log.method == "DELETE"
    assert log.path == "/v1/res/1"


def test_log_request_stores_status_code(logger: RequestLogger) -> None:
    log = logger.log_request("k1", "GET", "/", 404, 3, "1.2.3.4")
    assert log.status_code == 404


def test_log_request_stores_latency(logger: RequestLogger) -> None:
    log = logger.log_request("k1", "GET", "/", 200, 123, "1.2.3.4")
    assert log.latency_ms == 123


def test_log_request_stores_ip_address(logger: RequestLogger) -> None:
    log = logger.log_request("k1", "GET", "/", 200, 10, "10.20.30.40")
    assert log.ip_address == "10.20.30.40"


def test_analytics_empty_key_returns_zeros(logger: RequestLogger) -> None:
    result = logger.get_analytics("no-such-key")
    assert result["total_requests"] == 0
    assert result["success_rate"] == 0.0
    assert result["avg_latency_ms"] == 0.0


def test_analytics_total_requests_count(logger: RequestLogger) -> None:
    for i in range(5):
        logger.log_request("k2", "GET", "/v1/test", 200, i * 10, "1.1.1.1")
    result = logger.get_analytics("k2")
    assert result["total_requests"] == 5


def test_analytics_success_rate_is_float(logger: RequestLogger) -> None:
    logger.log_request("k3", "GET", "/", 200, 10, "1.1.1.1")
    result = logger.get_analytics("k3")
    assert isinstance(result["success_rate"], float)


def test_analytics_avg_latency_is_float(logger: RequestLogger) -> None:
    logger.log_request("k4", "GET", "/", 200, 100, "1.1.1.1")
    result = logger.get_analytics("k4")
    assert isinstance(result["avg_latency_ms"], float)


def test_analytics_success_rate_100_percent(logger: RequestLogger) -> None:
    for _ in range(4):
        logger.log_request("k5", "GET", "/", 200, 10, "1.1.1.1")
    result = logger.get_analytics("k5")
    assert result["success_rate"] == 1.0


def test_analytics_success_rate_partial(logger: RequestLogger) -> None:
    logger.log_request("k6", "GET", "/", 200, 10, "1.1.1.1")
    logger.log_request("k6", "GET", "/", 500, 10, "1.1.1.1")
    result = logger.get_analytics("k6")
    assert result["success_rate"] == 0.5


def test_analytics_avg_latency_calculation(logger: RequestLogger) -> None:
    logger.log_request("k7", "GET", "/", 200, 100, "1.1.1.1")
    logger.log_request("k7", "GET", "/", 200, 200, "1.1.1.1")
    result = logger.get_analytics("k7")
    assert result["avg_latency_ms"] == 150.0


def test_get_usage_by_path_empty(logger: RequestLogger) -> None:
    result = logger.get_usage_by_path("no-such-key")
    assert result == {}


def test_get_usage_by_path_groups_correctly(logger: RequestLogger) -> None:
    logger.log_request("k8", "GET", "/v1/payments", 200, 10, "1.1.1.1")
    logger.log_request("k8", "GET", "/v1/payments", 200, 10, "1.1.1.1")
    logger.log_request("k8", "POST", "/v1/kyc", 201, 20, "1.1.1.1")
    result = logger.get_usage_by_path("k8")
    assert result["/v1/payments"] == 2
    assert result["/v1/kyc"] == 1


def test_append_only_no_delete(logger: RequestLogger) -> None:
    """I-24: append-only — records persist after logging."""
    store = InMemoryRequestLogStore()
    rl = RequestLogger(store=store)
    rl.log_request("k9", "GET", "/", 200, 5, "1.1.1.1")
    rl.log_request("k9", "GET", "/", 200, 5, "1.1.1.1")
    logs = store.list_by_key("k9")
    assert len(logs) == 2  # both records present


def test_analytics_has_recent_logs_list(logger: RequestLogger) -> None:
    logger.log_request("k10", "GET", "/v1/test", 200, 10, "1.1.1.1")
    result = logger.get_analytics("k10")
    assert "recent_logs" in result
    assert isinstance(result["recent_logs"], list)
