# Changelog

## [2026-04-15]

### Improved
- Replaced the admin sidebar's old image-logo usage with a consistent Alash text mark, added a direct "Open public site" admin navigation link, and aligned public/admin entry screens with the same branding treatment
- Renamed the frontend package from `rag-web-ui-frontend` to `alash-chatbot-frontend` and localized the public chat's setup placeholder text

## [2026-04-14]

### Fixed
- Restored a no-op Alembic compatibility revision for deleted migration `c1d2e3f4a5b6` so existing Docker/MySQL databases that were already stamped with that revision can start successfully again
- Made the `d4e5f6a7b8c9` app-settings/public-chat migration idempotent so Docker deployments recover cleanly when `app_settings` or `chats.is_public` was already created during a previous partial migration run
- Stopped the frontend API helper from redirecting away from the login page on `401` responses from `/api/auth/token`, so invalid credentials and permission errors remain visible to the user
- Removed the MySQL `mysql_native_password` override from both Docker Compose files so new deployments use MySQL 8’s default auth setup instead of a legacy plugin path
- Restricted the authenticated product flow to admins by disabling public registration, requiring `is_superuser` for login, and enforcing admin-only checks on chat and knowledge-base API routes
- Replaced direct `crypto.randomUUID()` usage in KB upload UIs with a browser-safe client file ID helper so uploads still work in runtimes without that Web Crypto method
- Hardened knowledge-base uploads against duplicate content, duplicate file names, and duplicate task creation by returning per-file upload results, reusing existing identical documents, and refusing conflicting same-name uploads before processing
- Stopped the knowledge-base document list from briefly showing the same upload twice by merging pending tasks with processed documents via `document_id` and by preferring the latest processing-task status
- Made KB upload failures safer by cleaning up partial documents and MinIO objects when processing fails after a document record has already been created
- Updated both KB upload UIs to reconcile files by upload order/object identity instead of file name, so two files with the same name no longer overwrite each other's client-side status
- Hardened glossary XLSX parsing to tolerate removed optional columns, shifted or partially removed metadata rows, and non-active worksheet exports, while returning a cleaner validation error for invalid workbook files

### Added
- Added DB-backed app settings, a public chatbot KB selector, runtime-configurable public welcome text/provider/model fields, and dedicated unauthenticated public chat/config API endpoints
- Added a frontend route split with public `/` and `/chat` pages, admin routes under `/admin/...`, legacy redirects from `/login`, `/register`, and `/dashboard/...`, and a normal `Login` entry on the public site
- Added an admin settings page plus a knowledge-base action to mark exactly one KB as the active public chatbot knowledge base from the existing dashboard UI
- Added `backend/scripts/bootstrap_admin.py` to create or update the initial admin account now that public self-registration is disabled
- Added env-driven admin bootstrap via `ADMIN_USERNAME`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD`, with sample local/dev credentials in `.env.example`

## [2026-04-05]

### Added
- Added knowledge base export/import round-tripping as portable JSON snapshots, including KB metadata, stored documents, stored chunks, and original OCR source files
- Added an `Export KB` action on the knowledge-base detail page and an `Import KB` action on the knowledge-base list page so exported snapshots can be restored into a fresh knowledge base

### Improved
- Aligned the knowledge-base detail page actions so `Export KB` now sits beside `Upload documents` on the same row
- Switched TOC handling to an LLM-owned validation flow: candidate TOC pages are shown to the model explicitly, deterministic TOC enrichment/storage was removed, and TOC-only chunk retrieval is no longer exposed in the document viewer
- Expanded candidate TOC capture so the LLM can inspect longer multi-page tables of contents, up to roughly 5 consecutive TOC pages from the first detected heading

### Fixed
- Fixed a document-processing regression in `extract_pages()` where a loop counter shadowed the `BookIndex` object and caused `'int' object has no attribute 'metadata'` during OCR page chunk creation
- Kept failed document-processing rows visible after reload by returning failed tasks from the knowledge-base tasks endpoint and marking `DocumentUpload` records as failed when processing errors occur
- Restored `start_page - 1` through `end_page + 1` work extraction padding while keeping sparse OCR page mapping based on actual page numbers instead of list offsets
- Added an explicit `TOC find failed: ...` processing error when the LLM decides the extracted candidate TOC pages do not actually contain a valid table of contents

### Improved
- Updated the agent prompt and `get_work_content` tool guidance to warn that padded work extraction can include adjacent-context pages, so retrieval claims must be checked against the correct work/book/page before answering
- Updated the agent system prompt to favor clean, authentic Kazakh phrasing and to lightly mirror retrieved source writing style when it helps the answer

## [2026-04-04]

### Added
- First-class work/page retrieval metadata on `DocumentChunk` plus a migration to support raw page search and page-window inspection

### Improved
- Fixed OCR page-range extraction so sparse `ocr.json` files use actual page numbers instead of list offsets, and added a stored TOC section to document analysis plus the document viewer
- Added an `AGENT_VERBOSE` switch that turns on LangChain verbose mode and logs the exact final message payload plus raw model response for each agent LLM call
- Made catalog search results include explicit internal navigation IDs for authors/books/works so the agent can chain follow-up tool calls without inventing the wrong numbers
- Added a prompt rule requiring the agent to reuse internal IDs exactly as returned by search tools instead of guessing new ones
- Improved broad author-study handling so the agent is pushed to identify the author first, inspect author/work coverage more deeply, and avoid claiming multi-source research from a single catalog line
- Adjusted catalog-search ranking and labels so short author-like queries prefer author matches over work-title matches and expose the match type more clearly to the model
- Added a system-prompt rule to normalize Alash figure names in user-facing answers to `ұлы` / `қызы` forms instead of Russified `-ов/-ев/-ова/-ева` variants when possible
- Restructured the agent system prompt to favor deeper default research behavior, broader source gathering, multi-document comparison, and more comprehensive answers
- Increased the LangGraph recursion budget from 30 to 50 so research-heavy tool-calling turns can run longer before stopping
- Improved author-name retrieval tolerance by scoring common Kazakh/Russian surname suffix variants such as `-ов/-ев/-ұлы/-қызы`
- Tightened the agent prompt for broad author-study questions so it must inspect author/books/works before making synthesis claims instead of extrapolating from a single search result
- Fixed the document chunks modal endpoint to avoid MySQL sort-buffer exhaustion by fetching work chunks without DB-side sorting and ordering them in Python with a legacy fallback
- Made the database transcript the only durable chat-memory source by removing LangGraph checkpoint resume from chat turns and rebuilding history from persisted messages
- Added a non-vector retrieval layer for the agent with normalized keyword search over authors, books, works, plus filtered raw-page search for verification
- Stored cleaned raw OCR pages alongside work chunks during document processing so the agent can verify TOC-derived structure against source pages
- Kept the document chunk API compatible with the existing viewer by filtering page chunks out of the current document works endpoint
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
