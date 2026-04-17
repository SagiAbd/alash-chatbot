# alash-chatbot

RAG-based chatbot platform with multi-provider LLM and vector store support.

### Todo

- Set admin accounts  
- deploy  

### In Progress

- unify chat UI into top-level app shell with guest, user, and admin tiers
- add per-user personal library and sidebar chat history
- replace admin-only routing with shared `/`, `/knowledge`, `/library`, and `/settings`

### Done

- optimize `search_terms` with two-stage scoring
- hardcode Alihan Bokeihan TOC page offset on upload
- make the agent support Alash-style answers only after reading source works
- fix duplicate `document_chunks` primary keys for OCR uploads
- allow admin KB uploads to reuse the `ocr.json` file name when content differs
- add TOC indexing fallback flow: candidate TOC pages, then last 15 pages, then first 15 pages
- Add local login and registration  
- set admin and avg user permissions  
- add admin-only access, settings, and public chatbot kb selection  
- add public kazakh landing page and public chat  
- public + admin deployment split  
- remove rag web ui references alongside the app. its logo too  
- fix kb upload duplicates  
- fix bugs in kb upload  
- add glossary tool (fuzzy search over terms database)  
- add agent steps calling animation  
- enforce deeper work-level reading before broad author-study answers  
- make TOC validation LLM-only and fail explicitly when TOC detection is unreliable  
- add knowledge base export/import round-trip as JSON  
- improve llm answer style to docs style and kazakhi  
- warn agent that padded work content may include adjacent context  
- keep failed document-processing status visible after reload  
- fix page extraction shadowing regression in document loading  
- chatbot is lazy on tool calling.  
- remove raw page keyword search and keep direct page reading only
- strengthen prompt to say "I don't know" when specific claims lack evidence
- prioritize Ахмет, Әлихан, Міржақып first in public KB books and terms tabs
- rename visible app branding from Alash AI Assistant to Alash Science
- recheck document loading and TOC extraction  
- add AGENT_VERBOSE switch for full prompt logging  
- prevent wrong internal id guessing after catalog search  
- make author-study answers use author-first retrieval and deeper work inspection  
- normalize alash figure naming in answers to ұлы/қызы forms  
- restructure system prompt for deeper, more comprehensive research behavior  
- after reload the chat page, it errors with task canceled  
- animations and agent vis are bad. add support for advanced markdown, e.g tables  
- agent is too wordy, work with system prompt  
- improve author-name fuzzy matching and force evidence-first author study answers  
- fix document chunk modal query causing MySQL sort-memory errors  
- redesign chat state to use DB transcript only and add non-vector search + raw page verification  
- adapt rgis chat UI to our backend by hiding think tokens and restoring incremental token streaming  
- match think token rendering with rgis chat behavior  
- fix chat streaming and thinking dots behavior to match rgis expectations  
- align chat UI sizing, streaming, and loading animation with rgis frontend  
- copy rgis ai assistant frontend  
- agentic chat with deterministic document retrieval tools  
- agent thinking steps UI with animations  
- improve document upload and deletion  
- LLM-based book indexing with TOC extraction and per-work chunking  
- rich document viewer (metadata, summary, TOC, collapsible works)  
- fix event loop blocking during document processing  
- remove vector store from processing and retrieval paths  
- Clean ocr.json from hallucinations  
- Option of adding new sources by user  
- Give users option to see kb  
- Remove main page  
- TypeError: 'auth_provider' is an invalid keyword argument for User
- restrict guest chat access by session and hide raw chat/kb ids in UI
- process personal library pdf/docx uploads through OCR + book indexing and open them in the shared book viewer
