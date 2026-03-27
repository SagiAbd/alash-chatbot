"""Chat service — delegates to the LangGraph agent."""

import json
import logging
import time
from typing import AsyncGenerator, Dict, List

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chat import Message
from app.models.knowledge import Document, KnowledgeBase
from app.services.agent.graph import run_turn
from app.services.agent.llm_cache import _llm_cache
from app.services.agent.state import TurnLog
from app.services.agent.tools import create_tools
from app.services.embedding.embedding_factory import EmbeddingsFactory
from app.services.vector_store import VectorStoreFactory
from app.services.vector_store.base import BaseVectorStore

logger = logging.getLogger(__name__)

_SYSTEM_ERROR_KZ = "Кешіріңіз, жүйелік қате орын алды. Кейінірек қайталап көріңіз."

# ─── Module-level singleton caches ──────────────────────────────────
# Embeddings and vector stores are stateless at inference time —
# safe to share and reuse across requests.

_embeddings = None
_vector_store_cache: Dict[str, BaseVectorStore] = {}


def _get_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = EmbeddingsFactory.create()
    return _embeddings


def _get_vector_store(collection_name: str) -> BaseVectorStore:
    if collection_name not in _vector_store_cache:
        _vector_store_cache[collection_name] = VectorStoreFactory.create(
            store_type=settings.VECTOR_STORE_TYPE,
            collection_name=collection_name,
            embedding_function=_get_embeddings(),
        )
    return _vector_store_cache[collection_name]


# ─── Main entry point ────────────────────────────────────────────────


async def generate_response(
    query: str,
    messages: dict,
    knowledge_base_ids: List[int],
    chat_id: int,
    db: Session,
) -> AsyncGenerator[str, None]:
    """Generate a streaming response using the LangGraph agent.

    Flow per turn:
      1. Resolve vector stores from cache
      2. LLM decides to call search_kb or answer directly
      3. Tool executes vector search; LLM receives results and responds
      4. Tokens streamed back to client
    """
    try:
        pipeline_start = time.perf_counter()

        # Persist user message and create bot placeholder in one commit
        user_message = Message(content=query, role="user", chat_id=chat_id)
        bot_message = Message(content="", role="assistant", chat_id=chat_id)
        db.add(user_message)
        db.add(bot_message)
        db.commit()

        # Resolve knowledge bases
        knowledge_bases = (
            db.query(KnowledgeBase)
            .filter(KnowledgeBase.id.in_(knowledge_base_ids))
            .all()
        )

        # Build vector stores (from cache)
        vector_stores = []
        for kb in knowledge_bases:
            docs = db.query(Document).filter(Document.knowledge_base_id == kb.id).all()
            if docs:
                vector_stores.append(_get_vector_store(f"kb_{kb.id}"))

        if not vector_stores:
            error_msg = "Білім қоры таңдалмаған немесе бос."
            yield f"0:{json.dumps(error_msg)}\n"
            yield f"d:{json.dumps({'finishReason': 'stop', 'usage': {'promptTokens': 0, 'completionTokens': 0}})}\n"
            bot_message.content = error_msg
            db.commit()
            return

        # Build per-KB retrievers with k=6
        retrievers = [vs.as_retriever(search_kwargs={"k": 6}) for vs in vector_stores]

        # Build tools
        tools = create_tools(retrievers=retrievers)

        # Get LLM with tools bound (from cache).
        _llm_key = (settings.CHAT_PROVIDER, 0.0, True)
        llm = _llm_cache[_llm_key]
        llm_with_tools = llm.bind_tools(tools)

        # Build chat history from DB messages
        chat_history = []
        for i, msg in enumerate(messages["messages"]):
            # Skip current query if already last message
            if (
                i == len(messages["messages"]) - 1
                and msg["role"] == "user"
                and msg["content"] == query
            ):
                continue
            if msg["role"] == "user":
                chat_history.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                content = msg["content"]
                if "__LLM_RESPONSE__" in content:
                    content = content.split("__LLM_RESPONSE__")[-1]
                chat_history.append(AIMessage(content=content))

        # ═══ Stream the agent turn ═══
        full_response = ""
        turn_log = None

        async for item in run_turn(
            question=query,
            chat_history=chat_history,
            chat_id=chat_id,
            llm_with_tools=llm_with_tools,
            tools=tools,
        ):
            if isinstance(item, TurnLog):
                turn_log = item
            else:
                yield f"0:{json.dumps(item)}\n"
                full_response += item

        if turn_log:
            turn_log.pipeline_total_ms = (time.perf_counter() - pipeline_start) * 1000
            logger.info(
                "[TurnLog] iterations=%d tools=%s total_ms=%.0f",
                turn_log.iterations,
                turn_log.tool_calls,
                turn_log.pipeline_total_ms,
            )

        yield f"d:{json.dumps({'finishReason': 'stop', 'usage': {'promptTokens': 0, 'completionTokens': 0}})}\n"

        bot_message.content = full_response
        db.commit()

    except Exception as e:
        logger.exception("Error generating response for chat_id=%s: %s", chat_id, e)
        yield f"0:{json.dumps(_SYSTEM_ERROR_KZ)}\n"
        yield f"d:{json.dumps({'finishReason': 'error', 'usage': {'promptTokens': 0, 'completionTokens': 0}})}\n"
        if "bot_message" in locals():
            bot_message.content = _SYSTEM_ERROR_KZ
            db.commit()
    finally:
        db.close()
