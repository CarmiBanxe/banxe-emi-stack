#!/usr/bin/env python3
"""
BANXE AI BANK — Compliance Knowledge Base Ingestion Pipeline
Ingests 18 compliance documents from Google Drive (or local fallback)
into ChromaDB vector store for compliance AI agents.

Google Drive folder: 1BIGrPk5BlBz1m9d49j1hw3cgd3k5JTtl
Collection: banxe_compliance_kb
Embedding model: all-MiniLM-L6-v2

Usage:
    python scripts/ingest_compliance_drive.py [--local-only] [--dry-run]
"""

import argparse
from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
import re
import sys
import zipfile

# ── Logging setup ──────────────────────────────────────────────────────────────

LOG_PATH = Path("compliance_ingest.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

DRIVE_FOLDER_ID = "1BIGrPk5BlBz1m9d49j1hw3cgd3k5JTtl"
DOCS_DIR = Path("compliance_docs")
VECTORDB_DIR = Path("compliance_vectordb")
COLLECTION_NAME = "banxe_compliance_kb"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE_TOKENS = 1000
CHUNK_OVERLAP_TOKENS = 150
AGENT_CONTEXT_PATH = Path("agents/compliance/agent_context.json")

# Domain classification rules: (pattern, domain_tag)
DOMAIN_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"anti.financial.crime|afc", re.I), "aml_afc"),
    (re.compile(r"transaction.monitor", re.I), "transaction_monitoring"),
    (re.compile(r"pep|sanction|adverse.media|screening", re.I), "sanctions_pep"),
    (re.compile(r"cdd.manual|customer.due.diligence", re.I), "kyc_cdd"),
    (re.compile(r"anti.fraud|fraud.polic", re.I), "fraud_prevention"),
    (re.compile(r"anti.corruption|bribery|abc", re.I), "abc_anti_bribery"),
    (re.compile(r"consumer.duty", re.I), "consumer_duty"),
    (re.compile(r"safeguarding", re.I), "safeguarding"),
    (re.compile(r"country.risk|geographical.risk", re.I), "geo_risk"),
    (re.compile(r"cra\.b|risk.assessment", re.I), "risk_assessment"),
    (re.compile(r"payment.procedure", re.I), "payment_operations"),
    (re.compile(r"termination", re.I), "customer_operations"),
    (re.compile(r"management.information|mi.policy", re.I), "mi_governance"),
    (re.compile(r"mi.kri|kri.report", re.I), "kri_reporting"),
    (re.compile(r"rcc|risk.and.compliance.committee", re.I), "governance"),
    (re.compile(r"records.management", re.I), "records_management"),
    (re.compile(r"quality.assurance|qa\.", re.I), "quality_assurance"),
]


def classify_domain(filename: str) -> str:
    """Classify document domain based on filename."""
    for pattern, domain in DOMAIN_RULES:
        if pattern.search(filename):
            return domain
    return "general_compliance"


# ── Google Drive download ──────────────────────────────────────────────────────


def download_from_drive(folder_id: str, dest_dir: Path) -> list[Path]:
    """
    Download all files from a Google Drive folder.
    Requires: google-auth, google-api-python-client
    Env: GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_APPLICATION_CREDENTIALS
    """
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload

        creds_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not creds_path:
            raise OSError("GOOGLE_SERVICE_ACCOUNT_JSON not set")

        creds = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )
        service = build("drive", "v3", credentials=creds)

        results = (
            service.files()
            .list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id, name, mimeType)",
            )
            .execute()
        )

        files = results.get("files", [])
        log.info("Found %d files in Drive folder", len(files))
        dest_dir.mkdir(parents=True, exist_ok=True)
        downloaded: list[Path] = []

        for f in files:
            dest_path = dest_dir / f["name"]
            if dest_path.exists():
                log.info("  SKIP (exists): %s", f["name"])
                downloaded.append(dest_path)
                continue

            log.info("  Downloading: %s", f["name"])
            request = service.files().get_media(fileId=f["id"])
            with open(dest_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            downloaded.append(dest_path)

        return downloaded

    except ImportError:
        log.warning("google-api-python-client not installed — skipping Drive download")
        return []
    except Exception as exc:
        log.warning("Drive download failed: %s", exc)
        return []


def collect_local_files(docs_dir: Path) -> list[Path]:
    """Collect all supported files from local compliance_docs/ directory."""
    supported = {".pdf", ".docx", ".doc", ".zip", ".txt"}
    files = [p for p in docs_dir.iterdir() if p.suffix.lower() in supported]
    log.info("Found %d local files in %s", len(files), docs_dir)
    return files


# ── Parsing ────────────────────────────────────────────────────────────────────


def parse_pdf(path: Path) -> str:
    """Extract text from PDF using pypdf."""
    try:
        import pypdf

        reader = pypdf.PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages)
        log.info("  PDF: %s — %d pages, %d chars", path.name, len(reader.pages), len(text))
        return text
    except Exception as exc:
        log.error("  PDF parse error %s: %s", path.name, exc)
        return ""


def parse_docx(path: Path) -> str:
    """Extract text from DOCX using python-docx."""
    try:
        from docx import Document

        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs)
        log.info("  DOCX: %s — %d paragraphs, %d chars", path.name, len(paragraphs), len(text))
        return text
    except Exception as exc:
        log.error("  DOCX parse error %s: %s", path.name, exc)
        return ""


def parse_zip(path: Path, extract_dir: Path) -> str:
    """Extract and parse all supported files within a ZIP archive."""
    texts: list[str] = []
    try:
        with zipfile.ZipFile(path, "r") as zf:
            zf.extractall(extract_dir)
            for member in zf.namelist():
                member_path = extract_dir / member
                if member_path.suffix.lower() == ".pdf":
                    texts.append(parse_pdf(member_path))
                elif member_path.suffix.lower() in {".docx", ".doc"}:
                    texts.append(parse_docx(member_path))
                elif member_path.suffix.lower() == ".txt":
                    texts.append(member_path.read_text(errors="replace"))
        log.info("  ZIP: %s — extracted %d members", path.name, len(zf.namelist()))
    except Exception as exc:
        log.error("  ZIP parse error %s: %s", path.name, exc)
    return "\n".join(texts)


def parse_file(path: Path) -> str:
    """Dispatch parsing based on file extension."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return parse_pdf(path)
    elif ext in {".docx", ".doc"}:
        return parse_docx(path)
    elif ext == ".zip":
        extract_dir = path.parent / (path.stem + "_extracted")
        extract_dir.mkdir(exist_ok=True)
        return parse_zip(path, extract_dir)
    elif ext == ".txt":
        return path.read_text(errors="replace")
    else:
        log.warning("Unsupported format: %s", path.suffix)
        return ""


# ── Chunking ───────────────────────────────────────────────────────────────────


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token (GPT-style)."""
    return len(text) // 4


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE_TOKENS,
    overlap: int = CHUNK_OVERLAP_TOKENS,
) -> list[str]:
    """
    Split text into overlapping chunks of ~chunk_size tokens.
    Uses character-level splitting scaled by 4 chars/token.
    """
    char_size = chunk_size * 4
    char_overlap = overlap * 4
    step = char_size - char_overlap

    if len(text) <= char_size:
        return [text] if text.strip() else []

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + char_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += step

    log.debug("    Chunked into %d pieces (~%d tokens each)", len(chunks), chunk_size)
    return chunks


# ── Embeddings + ChromaDB ──────────────────────────────────────────────────────


def build_embedding_function() -> object:
    """Load sentence-transformers embedding function for ChromaDB."""
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    return SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")


def get_or_create_collection(persist_dir: Path) -> object:
    """Get or create ChromaDB persistent collection."""
    import chromadb

    client = chromadb.PersistentClient(path=str(persist_dir))
    ef = build_embedding_function()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,  # type: ignore[arg-type]
        metadata={"hnsw:space": "cosine"},
    )
    log.info("ChromaDB collection '%s' — %d existing docs", COLLECTION_NAME, collection.count())
    return collection


def ingest_chunks(
    collection: object,
    chunks: list[str],
    doc_name: str,
    domain: str,
    source_path: str,
) -> int:
    """Add chunks to ChromaDB. Returns number of chunks added."""
    if not chunks:
        return 0

    ids = [f"{doc_name}__chunk_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "source": source_path,
            "document": doc_name,
            "domain": domain,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "ingested_at": datetime.now(UTC).isoformat(),
        }
        for i in range(len(chunks))
    ]

    # ChromaDB upsert (idempotent)
    collection.upsert(  # type: ignore[attr-defined]
        ids=ids,
        documents=chunks,
        metadatas=metadatas,
    )
    return len(chunks)


# ── Agent context index ────────────────────────────────────────────────────────


def build_agent_context(
    doc_index: list[dict],
    output_path: Path,
) -> None:
    """
    Generate agent_context.json — index of all ingested documents
    for use in compliance agent SOUL files.
    """
    context = {
        "generated_at": datetime.now(UTC).isoformat(),
        "collection": COLLECTION_NAME,
        "embedding_model": EMBEDDING_MODEL,
        "total_documents": len(doc_index),
        "total_chunks": sum(d["chunks"] for d in doc_index),
        "domains": sorted({d["domain"] for d in doc_index}),
        "documents": doc_index,
        "agent_domain_map": {
            "mlro_agent": ["aml_afc", "governance", "kri_reporting", "mi_governance"],
            "aml_check_agent": ["aml_afc", "transaction_monitoring", "risk_assessment"],
            "sanctions_check_agent": ["sanctions_pep", "geo_risk", "aml_afc"],
            "jube_adapter_agent": ["transaction_monitoring", "fraud_prevention", "aml_afc"],
            "cdd_review_agent": ["kyc_cdd", "sanctions_pep", "risk_assessment"],
            "tm_agent": ["transaction_monitoring", "aml_afc", "fraud_prevention"],
            "fraud_detection_agent": [
                "fraud_prevention",
                "transaction_monitoring",
                "abc_anti_bribery",
            ],
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(context, indent=2))
    log.info("agent_context.json written → %s", output_path)


# ── Main pipeline ──────────────────────────────────────────────────────────────


def run(local_only: bool = False, dry_run: bool = False) -> None:
    log.info("=" * 60)
    log.info("BANXE Compliance KB Ingestion — %s", datetime.now(UTC).isoformat())
    log.info("=" * 60)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    VECTORDB_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Collect files
    if not local_only:
        log.info("Attempting Google Drive download (folder: %s)", DRIVE_FOLDER_ID)
        download_from_drive(DRIVE_FOLDER_ID, DOCS_DIR)

    files = collect_local_files(DOCS_DIR)
    if not files:
        log.warning(
            "No files found in %s — place PDFs/DOCXs there or provide Drive credentials", DOCS_DIR
        )
        return

    if dry_run:
        log.info("DRY RUN — listing files only:")
        for f in files:
            log.info("  %s → domain: %s", f.name, classify_domain(f.name))
        return

    # 2. Connect to ChromaDB
    collection = get_or_create_collection(VECTORDB_DIR)

    # 3. Process each file
    doc_index: list[dict] = []
    total_chunks = 0

    for path in sorted(files):
        domain = classify_domain(path.name)
        log.info("Processing: %s [domain=%s]", path.name, domain)

        text = parse_file(path)
        if not text.strip():
            log.warning("  Empty text — skipping %s", path.name)
            continue

        chunks = chunk_text(text)
        log.info("  → %d chunks (~%d tokens each)", len(chunks), CHUNK_SIZE_TOKENS)

        n = ingest_chunks(
            collection=collection,
            chunks=chunks,
            doc_name=path.stem,
            domain=domain,
            source_path=str(path),
        )
        total_chunks += n
        doc_index.append(
            {
                "filename": path.name,
                "stem": path.stem,
                "domain": domain,
                "chunks": n,
                "tokens_approx": estimate_tokens(text),
                "path": str(path),
            }
        )
        log.info("  ✓ %d chunks ingested", n)

    # 4. Build agent context index
    build_agent_context(doc_index, AGENT_CONTEXT_PATH)

    log.info("=" * 60)
    log.info("COMPLETE — %d documents, %d chunks total", len(doc_index), total_chunks)
    log.info("ChromaDB: %s", VECTORDB_DIR)
    log.info("Agent context: %s", AGENT_CONTEXT_PATH)
    log.info("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="BANXE Compliance KB Ingestor")
    parser.add_argument(
        "--local-only", action="store_true", help="Skip Google Drive, use local files only"
    )
    parser.add_argument("--dry-run", action="store_true", help="List files without ingesting")
    args = parser.parse_args()
    run(local_only=args.local_only, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
