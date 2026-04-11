# Prompt 17 Part 1/3 — EMI Compliance Knowledge Service

> **Feature**: Compliance Knowledge Base + NotebookLM MCP Integration
> **Ticket**: IL-CKS-01 | **Branch**: refactor/claude-ai-scaffold
> **Depends on**: Prompt 11 (MCP Server), Prompt 14 (Agent Routing)
> **All tools**: Open-source or free tier

---

## Context

Banxe EMI needs a centralized compliance knowledge service that ingests
EBA, FATF, FCA regulations, internal SOPs, historical SAR/STR reports,
and provides RAG-based Q&A for compliance officers and AI agents.
This replaces manual PDF lookups with structured MCP-accessible knowledge.

## Architecture

```
+-------------------+     +--------------------+     +------------------+
| Source Ingestion   |---->| Vector Store       |---->| MCP Knowledge    |
| (PDF/MD/URL)       |     | (ChromaDB local)   |     | Tools (6 tools)  |
+-------------------+     +--------------------+     +------------------+
        |                         |                          |
        v                         v                          v
+-------------------+     +--------------------+     +------------------+
| Document Parser    |     | Embedding Engine   |     | Query API        |
| (unstructured.io)  |     | (sentence-transformers) | (FastAPI + MCP)  |
+-------------------+     +--------------------+     +------------------+
```

## Phase 1 — Document Ingestion Pipeline

### 1.1 Create `services/compliance_kb/` directory structure

```
services/compliance_kb/
  __init__.py
  ingestion/
    __init__.py
    pdf_parser.py          # PyMuPDF + unstructured
    markdown_parser.py     # .md/.mdx files
    url_scraper.py         # Web page ingestion
    chunker.py             # Semantic chunking (512 tokens, 50 overlap)
  storage/
    __init__.py
    chroma_store.py        # ChromaDB local persistent
    models.py              # Document, Chunk, Source Pydantic models
  embeddings/
    __init__.py
    embedding_service.py   # sentence-transformers all-MiniLM-L6-v2
  config.py                # KB configuration
  constants.py             # Notebook IDs, tag taxonomy
```

### 1.2 Document Models (`storage/models.py`)

```python
from pydantic import BaseModel
from datetime import datetime
from enum import Enum

class SourceType(str, Enum):
    REGULATION = "regulation"
    GUIDANCE = "guidance"
    SOP = "sop"
    SAR_TEMPLATE = "sar_template"
    POLICY = "policy"
    CASE_STUDY = "case_study"

class Jurisdiction(str, Enum):
    EU = "eu"
    UK = "uk"
    FATF = "fatf"
    EBA = "eba"
    ESMA = "esma"

class ComplianceDocument(BaseModel):
    id: str                          # e.g. "eba-gl-2021-02"
    name: str
    source_type: SourceType
    jurisdiction: Jurisdiction
    version: str                     # ISO date
    tags: list[str]                  # ["aml", "kyc", "emi"]
    file_path: str | None = None
    url: str | None = None
    doc_count: int = 0
    sections: list[str] = []

class DocumentChunk(BaseModel):
    chunk_id: str
    document_id: str
    section: str
    text: str
    page: int | None = None
    char_start: int
    char_end: int
    metadata: dict = {}

class Citation(BaseModel):
    source_id: str
    source_type: SourceType
    title: str
    section: str
    snippet: str
    uri: str | None = None
    version: str
```

### 1.3 PDF Parser (`ingestion/pdf_parser.py`)

- Use PyMuPDF (fitz) for text extraction
- Fallback to unstructured.io for complex layouts
- Extract: title, sections, page numbers, tables
- Output: list[DocumentChunk]
- Handle: EBA guidelines, FATF recommendations, FCA handbooks

### 1.4 Semantic Chunker (`ingestion/chunker.py`)

- Chunk size: 512 tokens
- Overlap: 50 tokens
- Preserve section boundaries
- Add metadata: document_id, section, page, jurisdiction
- Support: English + Russian text

### 1.5 Embedding Service (`embeddings/embedding_service.py`)

- Model: sentence-transformers/all-MiniLM-L6-v2 (free, 384 dim)
- Batch embedding for ingestion
- Single embedding for queries
- Cache embeddings locally
- GPU support optional (CPU works fine for EMI scale)

### 1.6 ChromaDB Store (`storage/chroma_store.py`)

- Local persistent storage: `data/compliance_kb/chroma/`
- Collections per notebook: `emi-eu-aml`, `emi-uk-fca`, `emi-fatf`
- Metadata filtering: jurisdiction, source_type, tags, version
- Similarity search with score threshold (>0.7)
- Max results: configurable (default 10)

## Phase 2 — Compliance Notebooks (Pre-configured)

### 2.1 Create `config/compliance_notebooks.yaml`

```yaml
notebooks:
  emi-eu-aml:
    name: "EU AML/CTF Framework"
    description: "EBA/FATF AML directives and guidance"
    tags: ["emi", "aml", "regulator"]
    jurisdiction: eu
    sources:
      - id: eba-gl-2021-02
        name: "EBA Guidelines on ML/TF risk factors"
        type: regulation
        url: "https://eba.europa.eu/guidelines-mltf-risk-factors"
      - id: fatf-rec-2012
        name: "FATF 40 Recommendations"
        type: regulation
      - id: amld6-directive
        name: "6th Anti-Money Laundering Directive"
        type: regulation

  emi-uk-fca:
    name: "UK FCA EMI Regulations"
    description: "FCA handbook, CASS 15, PSR 2017"
    tags: ["emi", "fca", "uk"]
    jurisdiction: uk
    sources:
      - id: fca-cass-15
        name: "CASS 15 Safeguarding"
        type: regulation
      - id: psr-2017
        name: "Payment Services Regulations 2017"
        type: regulation
      - id: mlr-2017
        name: "Money Laundering Regulations 2017"
        type: regulation

  emi-internal-sop:
    name: "Banxe Internal SOPs"
    description: "Standard Operating Procedures for AML/KYC"
    tags: ["emi", "internal", "sop"]
    jurisdiction: eu
    sources:
      - id: banxe-kyc-sop
        name: "KYC Onboarding SOP"
        type: sop
      - id: banxe-aml-sop
        name: "AML Monitoring SOP"
        type: sop
      - id: banxe-sar-template
        name: "SAR Filing Template"
        type: sar_template

  emi-case-history:
    name: "Historical SAR/STR Reports"
    description: "Past suspicious activity reports and outcomes"
    tags: ["emi", "sar", "str", "history"]
    jurisdiction: eu
```

## Phase 3 — MCP Knowledge Tools (6 tools)

### 3.1 Register tools in `banxe_mcp/tools/compliance_kb.py`

Tool 1: `kb.list_notebooks`
- List all compliance notebooks with metadata
- Filter by tags, jurisdiction
- Return: id, name, description, doc_count, version

Tool 2: `kb.get_notebook`
- Get notebook details + source list
- Input: notebook_id
- Return: full notebook metadata + sources

Tool 3: `kb.query`
- RAG query against a notebook
- Input: notebook_id, question, context (jurisdiction, risk_level, product_type)
- Output: answer + citations with source_id, section, snippet, uri
- Max citations: 10
- Support English + Russian

Tool 4: `kb.search`
- Semantic search across notebook
- Input: notebook_id, query, limit
- Output: chunks with score, source metadata

Tool 5: `kb.compare_versions`
- Compare regulation versions (diff)
- Input: source_id, from_version, to_version, focus_sections
- Output: diff_summary, changes with section, change_type, impact_tags

Tool 6: `kb.get_citations`
- Get full citation details by IDs
- Input: citation_ids[]
- Output: full source metadata + text snippets

### 3.2 FastAPI endpoints (`api/routes/compliance_kb.py`)

```
POST /api/v1/kb/query          # RAG query
GET  /api/v1/kb/notebooks       # List notebooks
GET  /api/v1/kb/notebooks/{id}  # Get notebook
POST /api/v1/kb/search          # Semantic search
POST /api/v1/kb/compare         # Version compare
GET  /api/v1/kb/citations/{id}  # Get citations
POST /api/v1/kb/ingest          # Ingest document
GET  /api/v1/kb/health           # Health check
```

## Phase 4 — Tests (40+ tests)

### test files:
- `tests/test_compliance_kb/test_pdf_parser.py` (6 tests)
- `tests/test_compliance_kb/test_chunker.py` (5 tests)
- `tests/test_compliance_kb/test_chroma_store.py` (8 tests)
- `tests/test_compliance_kb/test_embedding_service.py` (4 tests)
- `tests/test_compliance_kb/test_mcp_tools.py` (10 tests)
- `tests/test_compliance_kb/test_api_routes.py` (8 tests)
- `tests/test_compliance_kb/test_notebooks_config.py` (3 tests)

### Key test scenarios:
- PDF parsing extracts correct sections from EBA guideline
- Chunker preserves section boundaries
- ChromaDB stores and retrieves with metadata filters
- MCP query returns answer with valid citations
- Version comparison detects regulatory changes
- API returns 200 with correct schema
- All notebooks in config are valid

## Phase 5 — Infrastructure Integration

### 5.1 Docker service (`docker/docker-compose.compliance-kb.yaml`)

```yaml
services:
  compliance-kb:
    build: ./services/compliance_kb
    ports:
      - "8098:8098"
    volumes:
      - compliance_kb_data:/app/data
    environment:
      - CHROMA_PERSIST_DIR=/app/data/chroma
      - EMBEDDING_MODEL=all-MiniLM-L6-v2
      - KB_CONFIG_PATH=/app/config/compliance_notebooks.yaml
    depends_on:
      - redis
```

### 5.2 Requirements (all free/OSS)

```
chromadb>=0.4.22
sentence-transformers>=2.2.2
PyMuPDF>=1.23.0
unstructured>=0.12.0
fastapi>=0.109.0
pydantic>=2.5.0
```

## Acceptance Criteria

- [ ] 4+ compliance notebooks configured (EU-AML, UK-FCA, Internal-SOP, Case-History)
- [ ] PDF/MD/URL ingestion pipeline works end-to-end
- [ ] ChromaDB stores vectors with metadata filtering
- [ ] 6 MCP tools registered and functional
- [ ] 8 FastAPI endpoints operational
- [ ] RAG query returns answer with citations (source_id + section + snippet)
- [ ] Version comparison shows regulatory changes
- [ ] 40+ tests passing
- [ ] Docker compose service runs standalone
- [ ] All dependencies are free/OSS

## Execution Order

1. Create directory structure
2. Implement Pydantic models
3. Build PDF parser + chunker
4. Set up ChromaDB store + embedding service
5. Create compliance notebooks config
6. Implement 6 MCP tools
7. Add FastAPI routes
8. Write tests
9. Docker compose
10. Integration test with existing MCP server

---

*Ticket: IL-CKS-01 | Prompt: 17 Part 1/3*
*Next: Part 2 — Experiment Copilot (Claude Code Action Agent)*
