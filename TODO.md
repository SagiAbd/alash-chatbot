# alash-chatbot

RAG-based chatbot platform with multi-provider LLM and vector store support.

### Todo
- agent is too wordy, work with system prompt
- animations and agent vis are bad
- after reload the chat page, it errors with task canceled
- change 15000 char page pagination with page numb
- for work too large cases: 1) summary 2) allow reading in 20 page chunks until enough info is gathered
- add 2 conv options: knowledge and alash figure style copier
- improve document processing by generating summaries to whole document
- add glossary tool (fuzzy search over terms database)

### In Progress


### Done ✓

- agentic chat with deterministic document retrieval tools
- agent thinking steps UI with animations
- improve document upload and deletion
- LLM-based book indexing with TOC extraction and per-work chunking
- rich document viewer (metadata, summary, TOC, collapsible works)
- fix event loop blocking during document processing
- remove vector store from processing and retrieval paths
- Clean ocr.json from hallucinations

