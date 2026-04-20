"""
api/routers/api_versioning.py — API Versioning REST endpoints
IL-AVD-01 | Phase 44 | banxe-emi-stack
9 endpoints under /v1/api-versions/
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from services.api_versioning.changelog_generator import ChangelogGenerator
from services.api_versioning.compatibility_checker import CompatibilityChecker
from services.api_versioning.deprecation_manager import DeprecationManager
from services.api_versioning.version_analytics import VersionAnalytics
from services.api_versioning.version_router import VersionRouter

router = APIRouter(tags=["api_versioning"])


@lru_cache(maxsize=1)
def _ver_router() -> VersionRouter:
    return VersionRouter()


@lru_cache(maxsize=1)
def _dep_mgr() -> DeprecationManager:
    return DeprecationManager()


@lru_cache(maxsize=1)
def _changelog() -> ChangelogGenerator:
    return ChangelogGenerator()


@lru_cache(maxsize=1)
def _compat() -> CompatibilityChecker:
    return CompatibilityChecker()


@lru_cache(maxsize=1)
def _analytics() -> VersionAnalytics:
    return VersionAnalytics()


def _vr_dep() -> VersionRouter:
    return _ver_router()


def _dm_dep() -> DeprecationManager:
    return _dep_mgr()


def _cl_dep() -> ChangelogGenerator:
    return _changelog()


def _cp_dep() -> CompatibilityChecker:
    return _compat()


def _an_dep() -> VersionAnalytics:
    return _analytics()


# ── GET /v1/api-versions/ — list versions + status ───────────────────────────


@router.get("/v1/api-versions/")
def list_versions(
    vr: Annotated[VersionRouter, Depends(_vr_dep)],
) -> dict[str, Any]:
    specs = vr.get_active_versions()
    return {
        "versions": [
            {
                "version": s.version.value,
                "status": s.status.value,
                "release_date": s.release_date,
                "sunset_date": s.sunset_date,
                "deprecation_notice_days": s.deprecation_notice_days,
            }
            for s in specs
        ]
    }


# ── GET /v1/api-versions/{version} — get version spec ────────────────────────


@router.get("/v1/api-versions/{version}")
def get_version(
    version: str,
    vr: Annotated[VersionRouter, Depends(_vr_dep)],
) -> dict[str, Any]:
    spec = vr.get_version_spec(version)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Version {version!r} not found"
        )
    return {
        "version": spec.version.value,
        "status": spec.status.value,
        "release_date": spec.release_date,
        "sunset_date": spec.sunset_date,
        "deprecation_notice_days": spec.deprecation_notice_days,
    }


# ── POST /v1/api-versions/{version}/deprecate — mark deprecated (HITL) ───────


@router.post("/v1/api-versions/{version}/deprecate", status_code=status.HTTP_202_ACCEPTED)
def deprecate_version(
    version: str,
    body: Annotated[dict[str, Any], Body()],
    dm: Annotated[DeprecationManager, Depends(_dm_dep)],
) -> dict[str, Any]:
    try:
        notice = dm.mark_deprecated(
            version=version,
            endpoint=body["endpoint"],
            sunset_date=body["sunset_date"],
            migration_endpoint=body["migration_endpoint"],
            actor=body.get("actor", "system"),
        )
        return {
            "notice_id": notice.notice_id,
            "version": notice.version.value,
            "endpoint": notice.endpoint,
            "sunset_date": notice.sunset_date,
            "migration_endpoint": notice.migration_endpoint,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# ── GET /v1/api-versions/deprecations — list all notices ──────────────────────


@router.get("/v1/api-versions/deprecations")
def list_deprecations(
    dm: Annotated[DeprecationManager, Depends(_dm_dep)],
) -> dict[str, Any]:
    notices = dm.get_all_deprecations()
    return {
        "deprecations": [
            {
                "notice_id": n.notice_id,
                "version": n.version.value,
                "endpoint": n.endpoint,
                "sunset_date": n.sunset_date,
                "migration_endpoint": n.migration_endpoint,
            }
            for n in notices
        ]
    }


# ── GET /v1/api-versions/deprecations/upcoming — sunsets in 30 days ──────────


@router.get("/v1/api-versions/deprecations/upcoming")
def upcoming_sunsets(
    dm: Annotated[DeprecationManager, Depends(_dm_dep)],
    days: int = 30,
) -> dict[str, Any]:
    notices = dm.check_approaching_sunset(days_threshold=days)
    return {
        "days_threshold": days,
        "upcoming": [
            {
                "notice_id": n.notice_id,
                "version": n.version.value,
                "endpoint": n.endpoint,
                "sunset_date": n.sunset_date,
            }
            for n in notices
        ],
    }


# ── GET /v1/api-versions/changelog — full changelog ──────────────────────────


@router.get("/v1/api-versions/changelog")
def full_changelog(
    cl: Annotated[ChangelogGenerator, Depends(_cl_dep)],
) -> dict[str, Any]:
    summary = cl.get_change_summary()
    return summary


# ── GET /v1/api-versions/changelog/{v1}/{v2} — diff between versions ─────────


@router.get("/v1/api-versions/changelog/{v_from}/{v_to}")
def version_diff(
    v_from: str,
    v_to: str,
    cl: Annotated[ChangelogGenerator, Depends(_cl_dep)],
) -> dict[str, Any]:
    markdown = cl.generate_changelog(v_from, v_to)
    guide = cl.generate_migration_guide(v_from, v_to)
    return {"changelog_markdown": markdown, "migration_guide": guide}


# ── GET /v1/api-versions/compatibility — compatibility matrix ─────────────────


@router.get("/v1/api-versions/compatibility")
def compatibility_matrix(
    cp: Annotated[CompatibilityChecker, Depends(_cp_dep)],
) -> dict[str, Any]:
    return cp.get_compatibility_matrix()


# ── GET /v1/api-versions/analytics/usage — version usage stats ───────────────


@router.get("/v1/api-versions/analytics/usage")
def usage_stats(
    an: Annotated[VersionAnalytics, Depends(_an_dep)],
) -> dict[str, Any]:
    return {
        "usage_by_version": an.get_usage_by_version(),
        "deprecated_usage": an.get_deprecated_usage(),
        "migration_pressure": an.generate_migration_pressure_report(),
        "sunset_risk": an.get_sunset_risk_report(),
    }
