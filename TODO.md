# alash-chatbot

RAG-based chatbot platform with multi-provider LLM and vector store support.

### Todo

- remove rag web ui references alongside the app. its logo too
- deploy  
- set admin and avg user permissions  

### In Progress


### Done

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
