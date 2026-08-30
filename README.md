# Secure Enterprise RAG Assistant

A portfolio-grade, production-ready Retrieval-Augmented Generation (RAG) platform with strict Role-Based Access Control (RBAC), document-level authorization boundaries, hybrid lexical and vector retrieval, local cross-encoder reranking, multi-layered prompt injection defenses, and rigorous automated evaluation.

---

## Architecture Overview

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2.
- **Database & Vectors**: PostgreSQL 16 with `pgvector` extension.
- **Hybrid Retrieval**: `pgvector` cosine similarity search combined with PostgreSQL `tsvector/tsquery` lexical search via Reciprocal Rank Fusion (RRF).
- **Security & Authorization**: Centralized document authorization policy enforced in database queries before context ranking or LLM generation.
- **Prompt Injection Defense**: Structured XML context boundaries, strict system-level untrusted-data instructions, and post-generation output leak validation.
- **Evaluation**: Custom evaluation suite measuring faithfulness, relevance, precision, recall, latency, and token cost tracking.

---

## Quickstart

### 1. Environment Configuration

Copy the example environment configuration:

```bash
cp .env.example .env
```

### 2. Virtual Environment Setup

Create and activate a project-local virtual environment:

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
python -m venv .venv
.\.venv\Scripts\activate.bat
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install pinned backend dependencies into the virtual environment:

```bash
pip install -r backend/requirements.txt
```

### 3. Running Database with Docker Compose

Start the PostgreSQL service with `pgvector`:

```bash
docker compose up -d db
```

Run database migrations:

```bash
python -m alembic -c backend/alembic.ini upgrade head
```

Start the FastAPI application:

```bash
python -m uvicorn backend.app.main:app --reload --port 8000
```

Access API documentation at `http://localhost:8000/docs`.

### 4. Running Automated Tests

Run the full test suite:

```bash
python -m pytest -v
```

---

## Development Phases

- **Phase 1A: Foundation & Database** (Current: Scaffold, config, async db engine, pgvector migration, health check, pytest suite).
- **Phase 1B: Authentication & RBAC** (JWT authentication, Admin & Employee roles, route security boundaries).
- **Phase 2: Document Ingestion, Centralized Auth Policy & MVP PII Baseline** (PDF parsing, recursive chunking, regex PII scrubber, embedding generation).
- **Phase 3: Hybrid Retrieval & Reranking** (Vector + lexical search, RRF merger, FlashRank reranker).
- **Phase 4: LLM Generation, Multi-layer Defenses & Citations** (Direct SDK LLM answer generation, source citations, adversarial prompt injection tests).
- **Phase 5: Frontend Experience** (React, Vite, TypeScript, Tailwind CSS UI).
- **Phase 6: Evaluation, Hardening & Docker Readiness** (RAG evaluation metrics, benchmarks, CI pipeline).
