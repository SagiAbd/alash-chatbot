# CLAUDE.md

## Project Overview

RAG-based chatbot platform (alash-chatbot). Users upload documents into knowledge bases, which are chunked, embedded, and stored in a vector database. A LangGraph agent handles retrieval-augmented chat with multi-turn context and source citations.

## Architecture

- **Backend:** FastAPI + SQLAlchemy (MySQL) + LangChain + LangGraph
- **Frontend:** Next.js 14 + TypeScript + Tailwind CSS + Shadcn/UI
- **Vector DB:** ChromaDB (default) or Qdrant
- **Object Storage:** MinIO (S3-compatible)
- **Reverse Proxy:** Nginx
- **Orchestration:** Docker Compose

### Backend Layout (`backend/app/`)

| Directory | Purpose |
|-----------|---------|
| `core/` | Config, JWT auth, MinIO client |
| `models/` | SQLAlchemy ORM (User, KnowledgeBase, Document, DocumentChunk, Message, APIKey) |
| `schemas/` | Pydantic request/response models |
| `api/api_v1/` | Main REST endpoints (auth, chat, knowledge base, API keys) |
| `api/openapi/` | External OpenAPI routes |
| `services/chat_service.py` | Chat logic delegating to the LangGraph agent |
| `services/document_processor.py` | Async document parsing, chunking, embedding |
| `services/agent/` | LangGraph agent (graph, state, tools, LLM cache) |
| `services/llm/llm_factory.py` | LLM provider factory (OpenAI, DeepSeek, Ollama, OpenRouter) |
| `services/embedding/embedding_factory.py` | Embedding provider factory |
| `services/vector_store/` | Vector store factory + ChromaDB/Qdrant implementations |

### Frontend Layout (`frontend/src/`)

| Directory | Purpose |
|-----------|---------|
| `app/` | Next.js App Router pages (dashboard, chat, knowledge, api-keys) |
| `components/ui/` | Shadcn/UI base components |
| `components/chat/` | Chat-specific components |
| `components/knowledge-base/` | Knowledge base & document upload components |
| `lib/` | Utility helpers |

## Key Environment Variables

Set in `.env` (copy from `.env.example`):

- `CHAT_PROVIDER` / `EMBEDDINGS_PROVIDER` — `openai`, `deepseek`, `ollama`, `openrouter`, `dashscope`
- `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY` — provider credentials
- `VECTOR_STORE_TYPE` — `chroma` (default) or `qdrant`
- `MYSQL_*` — database connection
- `MINIO_*` — object storage
- `SECRET_KEY` — JWT signing key

## Development

### Start all services (dev mode)

```bash
docker compose -f docker-compose.dev.yml up
```

### Backend (standalone)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend (standalone)

```bash
cd frontend
pnpm install
pnpm dev
```

## Code Conventions

- Factory pattern for LLM / embedding / vector store providers — add new providers there
- All document processing is async; use background tasks for heavy operations
- Agent logic lives in `services/agent/`; keep chat_service.py as a thin delegator

### Python Standards

- **Type hints** required on all new functions and classes, including return types
- **Docstrings** required on all public APIs (Args + Returns)
- **f-strings** exclusively — no `.format()` or `%`
- **88-char line limit** enforced by Ruff
- **Naming:** `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE_CASE` constants
- **Imports:** stdlib → third-party → local, alphabetical within groups

```bash
cd backend
ruff format .       # format
ruff check .        # lint
ruff check . --fix  # auto-fix
```

### Development Philosophy

- Early returns over nested conditions
- No abstractions until 2–3 real instances
- Only modify code directly related to the task — no opportunistic cleanup
- Validate only at system boundaries (user input, external APIs)

## Testing

Tests live in `backend/tests/`, mirroring source structure (e.g. `app/services/foo.py` → `tests/test_foo.py`).

```bash
cd backend
pytest                          # all tests
pytest tests/test_foo.py        # specific file
pytest tests/test_foo.py::test_bar  # specific test
pytest --cov=app                # with coverage
```

- Use **real database** for integration tests — no mocks (mock/prod divergence has caused incidents)
- Use pytest fixtures for setup/teardown
- One assertion concept per test; test behavior not internal state
- Add regression tests for every bug fix

## Git Workflow

Commit format: `type: short description` (present tense, no trailing period)

Types: `feat`, `fix`, `improve`, `refactor`, `test`, `docs`, `perf`

After every meaningful change: update [CHANGELOG.md](CHANGELOG.md) with a dated entry.
