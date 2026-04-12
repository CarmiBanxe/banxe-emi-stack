# Makefile — BANXE AI Bank EMI Stack
# IL-BIOME-01 | banxe-emi-stack
#
# Usage:
#   make lint            — run all linters (Ruff + Biome)
#   make lint-python     — Ruff only
#   make lint-frontend   — Biome only
#   make fix             — auto-fix everything
#   make test            — Python tests (no coverage)
#   make test-full       — Python tests with coverage
#   make test-frontend   — Vitest
#   make generate-component COMPONENT=MyButton   — Mitosis → React + Biome
#   make generate-all    — compile all .lite.tsx files
#   make quality-gate    — full gate: lint + semgrep + tests
#   make install         — install all dev deps

.PHONY: lint lint-python lint-frontend fix fix-python fix-frontend \
        test test-full test-frontend \
        generate-component generate-all \
        quality-gate install help

# ── Paths ─────────────────────────────────────────────────────────────────
FRONTEND_DIR := frontend
SRC_LITE_DIR := $(FRONTEND_DIR)/src
SRC_GEN_DIR  := $(FRONTEND_DIR)/src/generated

# ── Linting ───────────────────────────────────────────────────────────────

lint: lint-python lint-frontend
	@echo "✅ All linters passed"

lint-python:
	@echo "▶ Ruff lint..."
	ruff check .
	@echo "▶ Ruff format check..."
	ruff format --check .

lint-frontend:
	@echo "▶ Biome check (frontend)..."
	cd $(FRONTEND_DIR) && npx biome check .

# ── Auto-fix ──────────────────────────────────────────────────────────────

fix: fix-python fix-frontend
	@echo "✅ Auto-fix complete"

fix-python:
	@echo "▶ Ruff fix + format..."
	ruff check --fix .
	ruff format .

fix-frontend:
	@echo "▶ Biome apply (lint + format)..."
	cd $(FRONTEND_DIR) && npx biome check --apply .

# ── Tests ─────────────────────────────────────────────────────────────────

test:
	@echo "▶ Python tests (fast, no coverage)..."
	python3 -m pytest tests/ -x -q --override-ini=addopts=

test-full:
	@echo "▶ Python tests (with coverage ≥ 80%)..."
	python3 -m pytest tests/ -v --tb=short \
		--cov=services --cov=api \
		--cov-report=term-missing \
		--cov-fail-under=80

test-frontend:
	@echo "▶ Vitest..."
	cd $(FRONTEND_DIR) && npm run test

test-frontend-cov:
	@echo "▶ Vitest with coverage..."
	cd $(FRONTEND_DIR) && npm run test:cov

# ── Mitosis Code Generation ───────────────────────────────────────────────
# Usage: make generate-component COMPONENT=TransactionRow
#
# Pipeline:
#   1. Compile .lite.tsx → React (src/generated/)
#   2. Biome auto-fix the generated output
#   3. IMPORTANT: Review that EU AI Act Art.52 disclosure header is intact,
#      and tabular-nums / decimal-only logic was not altered by Biome.

generate-component:
ifndef COMPONENT
	$(error COMPONENT is required. Usage: make generate-component COMPONENT=MyButton)
endif
	@echo "▶ Compiling $(COMPONENT).lite.tsx → React..."
	cd $(FRONTEND_DIR) && npx @builder.io/mitosis-cli compile \
		--from=mitosis --to=react \
		$(SRC_LITE_DIR)/$(COMPONENT).lite.tsx \
		--out=$(SRC_GEN_DIR)/$(COMPONENT).tsx
	@echo "▶ Biome auto-fix generated output..."
	cd $(FRONTEND_DIR) && npx biome check --apply $(SRC_GEN_DIR)/$(COMPONENT).tsx
	@echo "✅ Generated: $(SRC_GEN_DIR)/$(COMPONENT).tsx"
	@echo "⚠️  Review: EU AI Act Art.52 header + tabular-nums + decimal-only logic"

# Compile all .lite.tsx files to all Mitosis targets
generate-all:
	@echo "▶ Compiling all .lite.tsx → react / vue / react-native..."
	cd $(FRONTEND_DIR) && find src -name "*.lite.tsx" | while read f; do \
		base=$$(basename $$f .lite.tsx); \
		npx @builder.io/mitosis-cli compile --from=mitosis --to=react $$f --out=$(SRC_GEN_DIR)/react/$$base.tsx; \
		npx @builder.io/mitosis-cli compile --from=mitosis --to=vue $$f --out=$(SRC_GEN_DIR)/vue/$$base.vue; \
		npx @builder.io/mitosis-cli compile --from=mitosis --to=react-native $$f --out=$(SRC_GEN_DIR)/native/$$base.tsx; \
	done
	@echo "▶ Biome fix all generated React output..."
	cd $(FRONTEND_DIR) && npx biome check --apply $(SRC_GEN_DIR)/react/
	@echo "✅ All components generated"

# ── Full Quality Gate ──────────────────────────────────────────────────────

quality-gate: lint
	@echo "▶ Semgrep (banxe custom rules)..."
	semgrep --config .semgrep/banxe-rules.yml --error
	@echo "▶ Python tests (fast)..."
	python3 -m pytest tests/ -x -q --override-ini=addopts=
	@echo "✅ Quality gate passed"

# ── Installation ─────────────────────────────────────────────────────────

install:
	@echo "▶ Python dev deps..."
	pip install -r requirements.txt
	pip install ruff semgrep pre-commit
	@echo "▶ Frontend deps..."
	cd $(FRONTEND_DIR) && npm install
	@echo "▶ Pre-commit hooks..."
	pre-commit install
	@echo "✅ All dependencies installed"

# ── Help ─────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "BANXE AI Bank — Developer Targets"
	@echo "──────────────────────────────────"
	@echo "  make lint                 Run Ruff + Biome"
	@echo "  make fix                  Auto-fix Ruff + Biome"
	@echo "  make test                 Python tests (fast)"
	@echo "  make test-full            Python tests + coverage"
	@echo "  make test-frontend        Vitest"
	@echo "  make generate-component COMPONENT=X  Mitosis → React + Biome"
	@echo "  make generate-all         Compile all .lite.tsx → React/Vue/RN"
	@echo "  make quality-gate         Full pre-merge check"
	@echo "  make install              Install all dev deps + pre-commit"
	@echo ""
