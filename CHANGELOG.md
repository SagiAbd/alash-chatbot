# Changelog

## [2026-03-28]

### Added
- LLM-based book indexing: extracts TOC, metadata, and per-work text segments from JSON OCR files
- Book content modal in document list: shows author, title, year, summary, TOC, and collapsible per-work text
- Cancel endpoint for pending/processing tasks (`DELETE /{kb_id}/tasks/{task_id}`)
- Per-document chunks endpoint (`GET /{kb_id}/documents/{doc_id}/chunks`)
- Tasks endpoint for page-reload-stable polling (`GET /{kb_id}/tasks`)
- `analysis` JSON column on `Document` model storing LLM-extracted book metadata

### Improved
- Document processing runs in a thread pool (`asyncio.to_thread`) — no longer blocks the event loop during LLM/MinIO/DB operations
- Processed files renamed to `Author - Title.json` in MinIO
- Upload zone replaced with compact button; auto-clears "queued" entries after 2 seconds
- Document display name shows "Author — Title" when analysis is available
- Works in modal sorted by page number; each work is individually collapsible; sections (Summary, TOC, Works) are collapsible
- Polling stops cleanly when all tasks complete; cancelling one task no longer stops polling for others
- "Added" timestamp correctly parsed as UTC (fixes 5-hour offset bug)

### Removed
- Vector store removed from all document processing, deletion, and retrieval paths
- ChromaDB service commented out in both docker-compose files
- `test-retrieval` endpoint removed

---

## [2026-03-27] (2)

### Improved
- Switched backend package manager from pip to uv — faster installs, reproducible lockfile (`uv.lock`)
- Added `pyproject.toml` with Ruff config; `requirements.txt` retained for reference only
- Updated `Dockerfile` and `Dockerfile.dev` to install uv and use `uv sync --frozen`

---

## [2026-03-27]

### Added
- CLAUDE.md with project overview, architecture reference, code standards, testing guide, and git workflow
- LangGraph-based agent service (`services/agent/`) with graph, state, tools, and LLM cache modules
- OpenRouter as a supported LLM and embeddings provider

### Improved
- `chat_service.py` refactored to delegate to the LangGraph agent — slimmer orchestration layer
- `document_processor.py` async processing improvements
- `embedding_factory.py` and `llm_factory.py` extended for new provider support
- `docker-compose.dev.yml` host networking fix for dev environments

---

## [2026-03-20]

### Fixed
- Removed duplicate `get_current_user` definition in `auth.py`; consolidated single definition in `security.py`

---

## [2025-12-08]

### Fixed
- Bumped Next.js from 14.2.25 to 14.2.32 in frontend (dependency update)

---

## [2025-11-15]

### Fixed
- Replaced `passlib` with direct `bcrypt` implementation to resolve compatibility issues

---

## [2025-08-30]

### Fixed
- Updated Docker configurations to use `host.docker.internal` for Ollama on macOS
- Updated `deploy-local.md` with Linux Docker host configuration notes

---

## [2025-04-16]

### Fixed
- Next.js patched from 14.1.0 to 14.2.5 to address CVE-2025-29927 (security)

---

## [2025-03-02]

### Added
- Optimized asynchronous document processing logic

### Fixed
- Database session handling in document processing (connection leaks)

### Refactored
- Dashboard and landing page UI redesigned

---

## [2025-02-25]

### Fixed
- Added `entrypoint.sh` to Dockerfile for proper service startup sequencing

---

## [2025-02-24]

### Added
- Auto-detection of whether Alembic migration is required at startup

---

## [2025-02-19]

### Added
- MySQL port configurable via environment variable (`MYSQL_PORT`)
- Default `api_base` and model values for DeepSeek in `.env.example`

---

## [2025-02-15]

### Added
- GitHub Actions workflow for service integration testing
- Nginx reverse proxy configuration and Docker Compose integration
