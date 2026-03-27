# CLAUDE.md

## Project Overview

RAG-based chatbot platform (alash-chatbot). Users upload documents into knowledge bases, which are chunked, embedded, and stored in a vector database. A LangGraph agent handles retrieval-augmented chat with multi-turn context and source citations. Supports multiple LLM providers (OpenAI, DeepSeek, Ollama, OpenRouter, DashScope) and vector stores (ChromaDB, Qdrant).

## Architecture

- **Backend:** FastAPI + SQLAlchemy (MySQL) + LangChain + LangGraph + Alembic
- **Frontend:** Next.js 14 + TypeScript + Tailwind CSS + Shadcn/UI + Vercel AI SDK
- **Vector DB:** ChromaDB (default) or Qdrant
- **Object Storage:** MinIO (S3-compatible)
- **Reverse Proxy:** Nginx
- **Orchestration:** Docker Compose

### Backend Layout (`backend/app/`)

| Path | Purpose |
|------|---------|
| `core/config.py` | App settings and environment variable loading |
| `core/security.py` | JWT auth, password hashing, current user dependency |
| `core/minio.py` | MinIO client for document object storage |
| `db/session.py` | SQLAlchemy session factory |
| `models/` | ORM models: User, KnowledgeBase, Document, DocumentChunk, Message, APIKey |
| `schemas/` | Pydantic request/response models |
| `api/api_v1/` | REST endpoints: auth, chat, knowledge base, API keys |
| `api/openapi/` | External OpenAPI routes |
| `services/chat_service.py` | Chat logic delegating to the LangGraph agent |
| `services/document_processor.py` | Async document parsing, chunking, embedding |
| `services/agent/` | LangGraph agent (graph, state, tools, LLM cache) |
| `services/llm/llm_factory.py` | LLM provider factory |
| `services/embedding/embedding_factory.py` | Embedding provider factory |
| `services/vector_store/` | Vector store factory + ChromaDB/Qdrant implementations |
| `startup/migarate.py` | Auto-run Alembic migrations on startup |

### Frontend Layout (`frontend/src/`)

| Path | Purpose |
|------|---------|
| `app/` | Next.js App Router pages (dashboard, login, register) |
| `app/dashboard/` | Main app shell with chat and knowledge base views |
| `components/chat/` | Chat UI components |
| `components/knowledge-base/` | Knowledge base and document upload components |
| `components/ui/` | Shadcn/UI base components |
| `lib/` | Utility helpers |

## Key Environment Variables

Set in `.env` (copy from `.env.example`):

- `CHAT_PROVIDER` / `EMBEDDINGS_PROVIDER` — `openai`, `deepseek`, `ollama`, `openrouter`, `dashscope`
- `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_EMBEDDINGS_MODEL` — OpenAI credentials
- `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL` — DeepSeek credentials
- `OLLAMA_API_BASE`, `OLLAMA_MODEL`, `OLLAMA_EMBEDDINGS_MODEL` — Ollama settings
- `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_EMBEDDINGS_MODEL` — OpenRouter credentials
- `DASH_SCOPE_API_KEY`, `DASH_SCOPE_EMBEDDINGS_MODEL` — DashScope credentials
- `VECTOR_STORE_TYPE` — `chroma` (default) or `qdrant`
- `CHROMA_DB_HOST` / `CHROMA_DB_PORT` — ChromaDB connection
- `QDRANT_URL` — Qdrant connection
- `MYSQL_SERVER`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` — database connection
- `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET_NAME` — object storage
- `SECRET_KEY` — JWT signing key
- `ACCESS_TOKEN_EXPIRE_MINUTES` — JWT expiry (default 10080 = 7 days)

## Development

### Start all services (dev mode)

```bash
docker compose -f docker-compose.dev.yml up
```

Services: nginx (port 80), backend (8000), frontend (3000), MySQL (3306), ChromaDB (8001), MinIO (9000/9001).

### Backend (standalone)

```bash
cd backend
uv sync               # install deps from uv.lock
uv run uvicorn app.main:app --reload --port 8000
```

To add/remove packages: edit `pyproject.toml` → `uv lock && uv sync`.

### Frontend (standalone)

```bash
cd frontend
pnpm install
pnpm dev
```

### Database migrations

```bash
cd backend
uv run alembic upgrade head                                  # apply migrations
uv run alembic revision --autogenerate -m "description"     # create new migration
```

## Code Conventions

- Factory pattern for LLM / embedding / vector store providers — add new providers in the respective factory files
- All document processing is async; use background tasks for heavy operations
- Agent logic lives in `services/agent/`; keep `chat_service.py` as a thin delegator
- Vector store, LLM, and embedding providers follow the abstract base class pattern — implement the interface, register in the factory

### Python Standards

- **Type hints** required on all new functions and classes, including return types
- **Docstrings** on all public APIs (Args + Returns)
- **f-strings** exclusively — no `.format()` or `%`
- **88-char line limit** enforced by Ruff
- **Naming:** `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE_CASE` constants
- **Imports:** stdlib → third-party → local, alphabetical within groups

```bash
cd backend
uv run ruff format .       # format
uv run ruff check .        # lint
uv run ruff check . --fix  # auto-fix
```

### Development Philosophy

- Early returns over nested conditions
- No abstractions until 2–3 real instances
- Only modify code directly related to the task — no opportunistic cleanup
- Validate only at system boundaries (user input, external APIs)
- No error handling for impossible scenarios — trust internal code and framework guarantees

## Testing

Tests in `backend/tests/`, mirroring source structure (e.g. `app/services/foo.py` → `tests/test_foo.py`).

```bash
cd backend
uv run pytest                               # all tests
uv run pytest tests/test_foo.py            # specific file
uv run pytest tests/test_foo.py::test_bar  # specific test
uv run pytest --cov=app                    # with coverage
```

- Use **real database** for integration tests — no mocks (mock/prod divergence has caused incidents)
- Use pytest fixtures for setup/teardown
- One assertion concept per test; test behavior not internal state
- Add regression tests for every bug fix

## Git Workflow

Commit format: `type: short description` (present tense, no trailing period, no body, no co-author trailers)

Types: `feat`, `fix`, `improve`, `refactor`, `test`, `docs`, `perf`

After every meaningful change: update [CHANGELOG.md](CHANGELOG.md) with a dated `## [YYYY-MM-DD]` entry.
