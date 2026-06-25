"""Unit tests for InMemoryOffsiteAdapter (ADR-029 Step 5).

Deterministic: injected clock + injected file_reader; no real filesystem,
no real S3/MinIO. Failure modes are exercised via the constructor knob.
"""

from __future__ import annotations

import pytest

from services.backup.factory import (
    OffsiteUploadConfig,
    get_offsite_upload_adapter,
)
from services.backup.in_memory_offsite_adapter import InMemoryOffsiteAdapter
from services.backup.offsite_upload_port import OffsiteObject


def _adapter(
    *,
    clock_value: float = 1000.0,
    file_bytes: bytes = b"\x00" * 42,
    failure_mode: str = "success",
) -> InMemoryOffsiteAdapter:
    return InMemoryOffsiteAdapter(
        clock=lambda: clock_value,
        file_reader=lambda _path: file_bytes,
        failure_mode=failure_mode,
    )


def test_upload_stores_object_and_returns_success() -> None:
    adapter = _adapter()
    result = adapter.upload("/local/dump.sql.gz", "s3://bucket/keycloak/dump.sql.gz")
    assert result.success is True
    assert result.remote_uri == "s3://bucket/keycloak/dump.sql.gz"
    assert result.size_bytes == 42
    assert result.error is None
    objs = adapter.list_objects("s3://bucket/")
    assert len(objs) == 1
    assert isinstance(objs[0], OffsiteObject)
    assert objs[0].uri == "s3://bucket/keycloak/dump.sql.gz"
    assert objs[0].size_bytes == 42


def test_upload_propagates_file_reader_exception_as_failure() -> None:
    def exploding_reader(_path: str) -> bytes:
        raise OSError("disk gone")

    adapter = InMemoryOffsiteAdapter(
        clock=lambda: 1000.0,
        file_reader=exploding_reader,
    )
    result = adapter.upload("/local/x", "s3://bucket/x")
    assert result.success is False
    assert result.size_bytes is None
    assert "OSError" in (result.error or "")
    assert "disk gone" in (result.error or "")
    # Failed uploads are NOT recorded in list_objects
    assert adapter.list_objects("s3://bucket/") == []


def test_upload_records_size_from_file_reader() -> None:
    adapter = _adapter(file_bytes=b"a" * 1024)
    result = adapter.upload("/local/x", "s3://bucket/x")
    assert result.success is True
    assert result.size_bytes == 1024
    assert adapter.list_objects("s3://bucket/")[0].size_bytes == 1024


def test_list_objects_filters_by_prefix() -> None:
    adapter = _adapter()
    adapter.upload("/local/kc", "s3://bucket/keycloak/2026/dump1")
    adapter.upload("/local/cl", "s3://bucket/clickhouse/2026/dump1")
    adapter.upload("/local/cl2", "s3://bucket/clickhouse/2026/dump2")

    kc = adapter.list_objects("s3://bucket/keycloak/")
    cl = adapter.list_objects("s3://bucket/clickhouse/")
    all_ = adapter.list_objects("s3://bucket/")
    nothing = adapter.list_objects("s3://other/")

    assert [o.uri for o in kc] == ["s3://bucket/keycloak/2026/dump1"]
    assert {o.uri for o in cl} == {
        "s3://bucket/clickhouse/2026/dump1",
        "s3://bucket/clickhouse/2026/dump2",
    }
    assert len(all_) == 3
    assert nothing == []


def test_list_objects_returns_sorted_desc_by_uploaded_at() -> None:
    clock = [1000.0]
    adapter = InMemoryOffsiteAdapter(
        clock=lambda: clock[0],
        file_reader=lambda _p: b"x",
    )
    adapter.upload("/a", "s3://bucket/a")  # uploaded_at = 1000
    clock[0] = 2000.0
    adapter.upload("/b", "s3://bucket/b")  # uploaded_at = 2000
    clock[0] = 1500.0
    adapter.upload("/c", "s3://bucket/c")  # uploaded_at = 1500

    objs = adapter.list_objects("s3://bucket/")
    # Sorted by uploaded_at DESC: b (2000) > c (1500) > a (1000)
    assert [o.uri for o in objs] == [
        "s3://bucket/b",
        "s3://bucket/c",
        "s3://bucket/a",
    ]


def test_upload_uses_injected_clock_for_uploaded_at() -> None:
    fixed = 1714000000.0
    adapter = _adapter(clock_value=fixed)
    result = adapter.upload("/local/x", "s3://bucket/x")
    assert result.uploaded_at == fixed
    assert adapter.list_objects("s3://bucket/")[0].uploaded_at == fixed


def test_upload_failure_mode_fail_returns_failure_without_storing() -> None:
    adapter = _adapter(failure_mode="fail")
    result = adapter.upload("/local/x", "s3://bucket/x")
    assert result.success is False
    assert result.size_bytes == 42  # read happened, just rejected
    assert "injected fail" in (result.error or "")
    assert adapter.list_objects("s3://bucket/") == []


def test_upload_failure_mode_raise_propagates_transport_error() -> None:
    adapter = _adapter(failure_mode="raise")
    with pytest.raises(RuntimeError, match="injected transport error"):
        adapter.upload("/local/x", "s3://bucket/x")


def test_factory_returns_none_when_OFFSITE_UPLOAD_ENABLED_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OFFSITE_UPLOAD_ENABLED", raising=False)
    get_offsite_upload_adapter.cache_clear()
    try:
        assert get_offsite_upload_adapter() is None
    finally:
        get_offsite_upload_adapter.cache_clear()


def test_factory_returns_in_memory_adapter_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OFFSITE_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("OFFSITE_UPLOAD_ADAPTER", "in_memory")
    get_offsite_upload_adapter.cache_clear()
    try:
        adapter = get_offsite_upload_adapter()
        assert isinstance(adapter, InMemoryOffsiteAdapter)
    finally:
        get_offsite_upload_adapter.cache_clear()


def test_factory_minio_branch_returns_none_until_provisioned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MinIO not provisioned yet (ADR-029 §1) — factory returns None (disabled)."""
    monkeypatch.setenv("OFFSITE_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("OFFSITE_UPLOAD_ADAPTER", "minio")
    get_offsite_upload_adapter.cache_clear()
    try:
        result = get_offsite_upload_adapter()
        assert result is None
    finally:
        get_offsite_upload_adapter.cache_clear()


def test_offsite_upload_config_defaults_when_env_absent() -> None:
    cfg = OffsiteUploadConfig.from_env()
    assert cfg.enabled is False
    assert cfg.adapter == "in_memory"
