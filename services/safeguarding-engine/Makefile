# Makefile — safeguarding-engine (FCA CASS 15 Safeguarding Engine)
#
# Self-contained install/test for this service. The root `make install` installs
# only the repo-root requirements.txt and does NOT install per-service packages,
# so the service's declared [project].dependencies (incl. structlog) + the
# [project.optional-dependencies].dev extras must be installed from here BEFORE tests.
#
# Usage (run from services/safeguarding-engine):
#   make install     — editable install of this package + dev extras (reproducible)
#   make test        — fast tests (no coverage gate)
#   make test-full   — tests with the pyproject coverage gate (--cov=app, ≥90%)
#   make lint        — ruff

.PHONY: install test test-full lint

install:
	python -m pip install -e ".[dev]"

test:
	python -m pytest -x -q --override-ini=addopts=

test-full:
	python -m pytest

lint:
	ruff check .
