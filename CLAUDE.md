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

- Follow the skills: `python-code-standards`, `development-philosophy`
- Factory pattern for LLM / embedding / vector store providers — add new providers there
- All document processing is async; use background tasks for heavy operations
- Agent logic lives in `services/agent/`; keep chat_service.py as a thin delegator
