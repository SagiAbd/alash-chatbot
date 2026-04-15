# alash-chatbot

Public-facing Kazakh chatbot plus an admin knowledge-base console for the
Alash corpus.

The project has two user experiences:

- Public site: a lightweight landing page and public chat at `/` and `/chat`
- Admin console: protected management flows at `/admin/...` for knowledge
  bases, chats, and public-chat settings
- Shared local sign-in and registration at `/login`, `/register`, and `/admin/login`

The backend uses FastAPI, SQLAlchemy, MySQL, MinIO, LangGraph, and multiple LLM
providers. The frontend uses Next.js 14, TypeScript, Tailwind CSS, and the
Vercel AI SDK.

## Important note

This codebase no longer uses vector-store retrieval.

- Do not use ChromaDB, Qdrant, or any vector store in this project
- Retrieval is being handled through the current non-vector, agent-driven flow
- Some legacy vector-store configuration still exists in `.env.example` and old
  compose comments, but it is not part of the intended runtime path

## Current product shape

### Public experience

- Kazakh landing page at `/`
- Public chat at `/chat`
- Each page refresh starts a new public chat session
- Public chat availability is controlled by admin settings
- Any locally registered user can sign in without gaining admin access automatically

### Admin experience

- Admin login at `/admin/login`
- Admin dashboard at `/admin`
- Knowledge-base management at `/admin/knowledge`
- Admin chat at `/admin/chat`
- Public-chat settings at `/admin/settings`
- Admin access is still controlled by the local database via `is_superuser`

### Backend capabilities

- Document upload and async processing
- Persistent chat transcripts
- Streaming answers
- Public chatbot KB selection
- Runtime-configurable welcome text and chat provider/model settings
- Admin bootstrap from env or CLI

## Architecture

### Backend

- FastAPI
- SQLAlchemy + MySQL
- LangChain + LangGraph
- MinIO object storage
- Alembic migrations

### Frontend

- Next.js 14 App Router
- TypeScript
- Tailwind CSS
- Shadcn/UI primitives
- Vercel AI SDK

### Storage and retrieval

- MySQL for application data
- MinIO for uploaded source files
- Non-vector retrieval path for the chatbot

## Quick start

### Prerequisites

- Docker and Docker Compose v2+
- Node.js 18+
- Python 3.9+

### 1. Configure environment variables

```bash
cp .env.example .env
```

At minimum, review and set:

- `CHAT_PROVIDER`
- provider API keys and model vars for the provider you choose
- `SECRET_KEY`
- `ADMIN_USERNAME`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`

### 2. Start the dev stack

```bash
docker compose -f docker-compose.dev.yml up --build
```

### 3. Open the app

- Public site: `http://127.0.0.1.nip.io`
- Public chat: `http://127.0.0.1.nip.io/chat`
- Shared login: `http://127.0.0.1.nip.io/login`
- Shared registration: `http://127.0.0.1.nip.io/register`
- Admin login: `http://127.0.0.1.nip.io/admin/login`
- API docs: `http://127.0.0.1.nip.io/redoc`
- OpenAPI JSON: `http://127.0.0.1.nip.io/openapi.json`
- MinIO console: `http://127.0.0.1.nip.io:9001`

## Local development

### Full stack

```bash
docker compose -f docker-compose.dev.yml up
```

### Backend only

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

### Frontend only

```bash
cd frontend
pnpm install
pnpm dev
```

## Admin bootstrap

The backend automatically attempts to create or update the initial local admin
user from:

- `ADMIN_USERNAME`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`

You can also bootstrap manually:

```bash
cd backend
uv run python scripts/bootstrap_admin.py \
  --username admin \
  --email admin@example.com \
  --password Admin12345
```

## Configuration highlights

### LLM providers

Supported chat/provider configuration in this repo includes:

- OpenAI
- DeepSeek
- Ollama
- OpenRouter
- DashScope

The active chat provider is selected with `CHAT_PROVIDER`.

### App settings

Admin settings persist:

- `public_kb_id`
- `chat_provider`
- `chat_model`
- `welcome_title`
- `welcome_text`

### Auth configuration

Local JWT-based auth uses:

- `SECRET_KEY`
- `ACCESS_TOKEN_EXPIRE_MINUTES`

Initial admin seeding uses:

- `ADMIN_USERNAME`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`

## Project layout

```text
backend/
  app/
    api/api_v1/         API routes
    core/               config, security, MinIO
    models/             SQLAlchemy models
    schemas/            Pydantic schemas
    services/           chat, agent, document processing, settings
    startup/            startup migration flow
  scripts/
    bootstrap_admin.py  create/update admin user

frontend/
  src/app/              Next.js routes
  src/components/       UI components
  src/lib/              API helpers and utilities
```

## Notes for contributors

- Keep the public/admin split intact
- Treat server-side auth as authoritative
- Do not reintroduce vector-store retrieval
- Keep `TODO.md` updated when working on tracked tasks
- Update `CHANGELOG.md` after meaningful changes

## License

This project is licensed under the [Apache-2.0 License](LICENSE).
