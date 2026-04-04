# Changelog

## [2026-04-04]

### Improved
- Refined the chat page UX with smarter auto-scroll behavior, auto-resizing input, simplified assistant message rendering, and smoother loading/message animations
- Upgraded chat markdown rendering with raw HTML support, bracketed URL normalization, styled tables/code/quotes/lists, and token-by-token streaming output animation
- Matched the chat UI more closely to the RGIS frontend by restoring the larger answer text size and preventing loading dots from overlapping with the streaming assistant bubble
- Matched the chat textarea typography more closely to generated answers by using the same visual text scale and line height
- Fixed the chat stream so hidden think phases keep showing the 3-dot loading state and visible answer text animates in smoothly instead of appearing all at once
- Matched `<think>` token handling to the RGIS chat flow so think blocks render through the markdown pipeline and streaming state follows the last assistant message consistently
- Adapted the RGIS chat UI to our backend by filtering visible `<think>` output on the frontend and streaming agent text chunks immediately from the backend graph instead of buffering the full answer
- Expanded `AGENTS.md` with `TODO.md` workflow rules, iterative delivery guidance, and a requirement to suggest a commit message after changes
- Aligned `TODO.md` section naming with the documented plain-list workflow

## [2026-04-01]

### Improved
- Structured backend chat logs into an ordered turn timeline with sequence numbers, LangGraph/LLM/tool stages, per-tool timing, and explicit parallel batch markers
- Reduced noisy LangChain debug logging and switched backend log formatting to a denser, easier-to-scan layout

## [2026-03-28] (2)

### Refactored
- Cleaned and standardized backend codebase formatting using Ruff (fixed indentation, removed redundant lines)

### Changed
- Chat agent rewritten from vector-store RAG to agentic approach with deterministic document retrieval
- New agent tools: `get_authors_and_books`, `get_book_details`, `get_author_works`, `get_work_content` (with pagination)
- Agent streams step events (thinking, tool calls, results) to frontend in real-time
- Parallel tool execution via `asyncio.gather` + LLM instructed to use parallel calls
- Graph recursion limit increased from 10 to 30
- System prompt instructs compact answers by default (verbose only when user asks)
- Chat UI redesigned with separate visual blocks: collapsible ThinkingBubble, animated ToolCallCard, Answer
- User message font size matches LLM output (both use `prose-sm`)
- Added scroll padding at bottom so last line is never cut off
- framer-motion for all message/step animations
- Answer component simplified — removed citation popovers, LLM now cites inline
- Removed all vector store imports from chat service

---

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
