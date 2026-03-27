"""Tools for the Alash RAG agent.

Single tool: search_kb — LLM writes an expanded query, simple vector search
returns relevant document chunks from all selected knowledge bases.
"""

from langchain_core.tools import tool
from langchain.retrievers.merger_retriever import MergerRetriever


def create_tools(retrievers: list):
    """Create tool instances with the retriever bound via closure.

    Args:
        retrievers: List of vector store retrievers (one per selected KB).

    Returns:
        List of LangChain tool instances ready for bind_tools().
    """
    merger = MergerRetriever(retrievers=retrievers)

    @tool
    async def search_kb(query: str) -> str:
        """Search the Alash knowledge base to find relevant information.

        ALWAYS call this tool before answering any question about the Alash
        movement, its members, their research, books, or history.

        Expand the user's question into a comprehensive search query:
        add synonyms, related terms, and alternative phrasings.
        Example: «Aхмет Байтұрсынов» → «Ахмет Байтұрсынов Алаш Орда ақын ғалым тілші»

        Args:
            query: Expanded, keyword-rich search query (not the raw user message)
        """
        try:
            docs = await merger.ainvoke(query)
        except Exception as e:
            return f"Қате: {e}"

        if not docs:
            return "Білім қорынан ешқандай ақпарат табылмады."

        parts = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "")
            page = doc.metadata.get("page", "")
            header = f"[{i}]"
            if source or page:
                header += f" (Дереккөз: {source}, Бет: {page})"
            parts.append(f"{header}\n{doc.page_content}")

        return "\n\n---\n\n".join(parts)

    return [search_kb]
