# Prompt 15 — Design-to-Code Pipeline (D2C)

> Ticket: IL-D2C-01 | Branch: refactor/claude-ai-scaffold
> Architecture: docs/ARCHITECTURE-DESIGN-TO-CODE.md
> Date: 2026-04-11

## Goal

Build an open-source design-to-code pipeline using Penpot MCP Server,
Style Dictionary, Mitosis, and AI orchestration (FastAPI + LangChain + Ollama)
to automate UI generation for BANXE web and mobile platforms.

## Reference

Read `docs/ARCHITECTURE-DESIGN-TO-CODE.md` before starting.
Follow existing project patterns from `services/`, `config/`, `infra/`.

## Phase 1 — Penpot Self-Hosted Deployment

Create `infra/penpot/docker-compose.yml`:
```yaml
services:
  penpot-frontend:
    image: penpotapp/frontend:latest
    ports: ["9001:80"]
    depends_on: [penpot-backend, penpot-exporter]
  penpot-backend:
    image: penpotapp/backend:latest
    environment:
      PENPOT_FLAGS: enable-registration enable-login-with-password enable-smtp enable-prepl-server
      PENPOT_PUBLIC_URI: http://localhost:9001
      PENPOT_DATABASE_URI: postgresql://penpot_db/penpot
      PENPOT_REDIS_URI: redis://penpot_redis/0
      PENPOT_ASSETS_STORAGE_BACKEND: assets-fs
      PENPOT_STORAGE_ASSETS_FS_DIRECTORY: /opt/data/assets
    depends_on: [penpot_db, penpot_redis]
  penpot-exporter:
    image: penpotapp/exporter:latest
  penpot_db:
    image: postgres:16
    environment:
      POSTGRES_DB: penpot
      POSTGRES_USER: penpot
      POSTGRES_PASSWORD: penpot
  penpot_redis:
    image: redis:7-alpine
```

Create `infra/penpot/README.md` with setup instructions.
Add to main `docker/docker-compose.yml` as optional profile.

## Phase 2 — Penpot MCP Client

Create `services/design_pipeline/__init__.py`
Create `services/design_pipeline/penpot_client.py`:

```python
class PenpotMCPClient:
    """Client for Penpot MCP Server / REST API"""
    def __init__(self, base_url: str, token: str):
        # base_url = e.g. http://localhost:9001
        # token = Penpot access token

    async def get_project_files(self, project_id: str) -> list[dict]
    async def get_file_components(self, file_id: str) -> list[Component]
    async def get_design_tokens(self, file_id: str) -> DesignTokenSet
    async def get_page_structure(self, file_id: str, page_id: str) -> PageTree
    async def get_component_svg(self, file_id: str, component_id: str) -> str
    async def export_frame(self, file_id: str, frame_id: str, format: str) -> bytes
```

Create `services/design_pipeline/models.py`:
- Component, DesignTokenSet, PageTree, DesignLayer
- ColorToken, TypographyToken, SpacingToken
- LayoutConstraint, AutoLayoutConfig

## Phase 3 — Design Token Pipeline

Create `services/design_pipeline/token_extractor.py`:
- Extract tokens from Penpot via MCP client
- Transform to Style Dictionary format
- Output: JSON tokens file

Create `config/design-tokens/banxe-tokens.json`:
```json
{
  "color": {
    "primary": { "value": "#1A73E8" },
    "secondary": { "value": "#34A853" },
    "danger": { "value": "#EA4335" },
    "warning": { "value": "#FBBC04" },
    "surface": { "value": "#FFFFFF" },
    "background": { "value": "#F8F9FA" }
  },
  "typography": {
    "heading-1": { "value": { "fontSize": "32px", "fontWeight": 700, "lineHeight": 1.2 } },
    "body": { "value": { "fontSize": "16px", "fontWeight": 400, "lineHeight": 1.5 } }
  },
  "spacing": {
    "xs": { "value": "4px" },
    "sm": { "value": "8px" },
    "md": { "value": "16px" },
    "lg": { "value": "24px" },
    "xl": { "value": "32px" }
  }
}
```

Create `config/design-tokens/style-dictionary.config.json`:
- Build targets: css, tailwind, json, react-native
- Output paths for each platform

## Phase 4 — AI Orchestrator Service

Create `services/design_pipeline/orchestrator.py`:

```python
class DesignToCodeOrchestrator:
    """AI-powered design-to-code pipeline"""
    def __init__(self, penpot_client, llm, code_generator):
        self.penpot = penpot_client
        self.llm = llm  # Ollama via LangChain
        self.generator = code_generator

    async def generate_component(self, file_id, component_id, framework="react"):
        # 1. Get design context from Penpot MCP
        context = await self.penpot.get_component_context(component_id)
        # 2. Get design tokens
        tokens = await self.penpot.get_design_tokens(file_id)
        # 3. LLM analyzes layout and generates Mitosis JSX
        prompt = self.build_prompt(context, tokens, framework)
        code = await self.llm.agenerate(prompt)
        # 4. Compile via Mitosis to target framework
        compiled = self.generator.compile(code, framework)
        # 5. Visual QA comparison
        passed = await self.visual_qa(component_id, compiled)
        return GenerationResult(code=compiled, qa_passed=passed)

    async def sync_tokens(self, file_id):
        tokens = await self.penpot.get_design_tokens(file_id)
        self.token_extractor.export_to_style_dictionary(tokens)
        # Run style-dictionary build
        subprocess.run(["npx", "style-dictionary", "build"])

    async def generate_page(self, file_id, page_id, framework="react"):
        structure = await self.penpot.get_page_structure(file_id, page_id)
        # Break into components, generate each, assemble layout
        ...
```

Create `services/design_pipeline/api.py` (FastAPI router):
- POST /design/generate-component
- POST /design/generate-page
- POST /design/sync-tokens
- POST /design/visual-compare
- GET /design/components/{file_id}
- GET /design/tokens/{file_id}

## Phase 5 — Code Generator (Mitosis Bridge)

Create `services/design_pipeline/code_generator.py`:
- MitosisGenerator class
- Input: Mitosis JSX (generated by LLM)
- Output: compiled React/Vue/RN/Angular code
- Uses @builder.io/mitosis CLI
- Fallback: direct React/Tailwind generation

Create `services/design_pipeline/templates/`:
- component.mitosis.tsx.j2 - Jinja2 template for Mitosis JSX
- page.mitosis.tsx.j2 - page layout template
- banxe-component.tsx.j2 - BANXE-specific patterns (forms, tables, cards)

## Phase 6 — Visual QA Agent

Create `services/design_pipeline/visual_qa.py`:
- Render generated component via Puppeteer/Playwright
- Screenshot the rendered output
- Compare with Penpot exported frame (ResembleJS/pixelmatch)
- Return: similarity score, diff image, pass/fail
- Threshold: 95% similarity = pass

Create `services/design_pipeline/qa_runner.py`:
- BackstopJS config generation
- Loki integration for Storybook snapshots
- CI/CD hook for GitHub Actions

## Phase 7 — BANXE UI Agents

Create `services/design_pipeline/agents/` directory:
- `compliance_ui_agent.py` - KYC/AML form generation from schemas
- `transaction_ui_agent.py` - payment flow screens (PSD2 SCA)
- `report_ui_agent.py` - FIN060/SAR report layout generation
- `onboarding_agent.py` - step-by-step KYC flows

Each agent uses DesignToCodeOrchestrator with domain-specific prompts
and BANXE compliance component library from Penpot.

## Phase 8 — Tests

Create `tests/test_design_pipeline/`:
- `test_penpot_client.py` - Penpot API/MCP calls (mocked)
- `test_token_extractor.py` - token extraction + Style Dictionary
- `test_code_generator.py` - Mitosis compilation
- `test_orchestrator.py` - end-to-end pipeline
- `test_visual_qa.py` - screenshot comparison logic
- `test_agents.py` - BANXE UI agents
- `test_api.py` - FastAPI endpoints

Minimum 80 tests. All must pass. Coverage >= 80%.

## Phase 9 — MCP Tools Integration

Add to `banxe_mcp/tools/`:
- `generate_component` - generate UI component from Penpot design
- `sync_design_tokens` - sync tokens from Penpot to codebase
- `visual_compare` - compare implementation vs design
- `list_design_components` - list available Penpot components

Register in `.ai/registries/mcp-tools.yaml`.

## Phase 10 — Grafana Dashboard

Create `infra/grafana/dashboards/design-pipeline-metrics.json`:
- Components generated (count, framework, agent)
- Token sync frequency
- Visual QA pass/fail ratios
- LLM token usage per generation
- Average generation latency

## Files Checklist

```
infra/penpot/docker-compose.yml
infra/penpot/README.md
services/design_pipeline/__init__.py
services/design_pipeline/models.py
services/design_pipeline/penpot_client.py
services/design_pipeline/token_extractor.py
services/design_pipeline/orchestrator.py
services/design_pipeline/code_generator.py
services/design_pipeline/visual_qa.py
services/design_pipeline/qa_runner.py
services/design_pipeline/api.py
services/design_pipeline/templates/component.mitosis.tsx.j2
services/design_pipeline/templates/page.mitosis.tsx.j2
services/design_pipeline/templates/banxe-component.tsx.j2
services/design_pipeline/agents/__init__.py
services/design_pipeline/agents/compliance_ui_agent.py
services/design_pipeline/agents/transaction_ui_agent.py
services/design_pipeline/agents/report_ui_agent.py
services/design_pipeline/agents/onboarding_agent.py
config/design-tokens/banxe-tokens.json
config/design-tokens/style-dictionary.config.json
config/penpot/penpot-config.yaml
infra/grafana/dashboards/design-pipeline-metrics.json
tests/test_design_pipeline/ (7+ files, 80+ tests)
```

## Infrastructure Utilization Canon

- [x] Penpot: self-hosted design tool (Docker)
- [x] PostgreSQL: Penpot backend DB
- [x] Redis: Penpot cache
- [x] FastAPI: Design Pipeline API
- [x] Ollama: local LLM for code generation
- [x] ClickHouse: pipeline metrics
- [x] Grafana: design pipeline dashboard
- [x] Docker: Penpot + pipeline services
- [x] MCP: 4 new tools + Penpot MCP Server
- [x] Style Dictionary: token transformation

## Verification

1. `ruff check .` - zero warnings
2. `pytest tests/test_design_pipeline/ -v` - 80+ tests green
3. `coverage report` - >= 80%
4. Penpot Docker starts successfully
5. Token extraction produces valid JSON + CSS + Tailwind
6. MCP tools callable via banxe_mcp
7. Grafana dashboard JSON valid

---
*Created: 2026-04-11 | Ticket: IL-D2C-01 | Prompt: 15*
