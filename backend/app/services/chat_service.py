"""Chat service — delegates to the LangGraph agent with deterministic tools."""

import json
import logging
import time
from typing import AsyncGenerator, List

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chat import Message
from app.models.knowledge import Document
from app.services.agent.graph import run_turn
from app.services.agent.llm_cache import _llm_cache
from app.services.agent.state import TurnLog
from app.services.agent.tools import create_tools

logger = logging.getLogger(__name__)

_SYSTEM_ERROR_KZ = "Кешіріңіз, жүйелік қате орын алды. Кейінірек қайталап көріңіз."

_EMPTY_USAGE = {"promptTokens": 0, "completionTokens": 0}


def _finish_event(reason: str = "stop") -> str:
    """Build a Vercel AI finish event line."""
    payload = {"finishReason": reason, "usage": _EMPTY_USAGE}
    return f"d:{json.dumps(payload)}\n"


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
      1. Build deterministic tools from DB documents
      2. LLM decides which tools to call (browse authors/books/works)
      3. Tools execute DB queries; LLM receives results and responds
      4. Tokens and step events streamed back to client
    """
    try:
        pipeline_start = time.perf_counter()
        turn_log = TurnLog()
        turn_log.add_event(
            "turn.start",
            "Chat turn started",
            knowledge_base_ids=knowledge_base_ids,
            message_count=len(messages.get("messages", [])),
        )

        # Persist user message and create bot placeholder in one commit
        user_message = Message(content=query, role="user", chat_id=chat_id)
        bot_message = Message(content="", role="assistant", chat_id=chat_id)
        db.add(user_message)
        db.add(bot_message)
        db.commit()

        # Check that KBs have documents
        doc_count = (
            db.query(Document)
            .filter(Document.knowledge_base_id.in_(knowledge_base_ids))
            .count()
        )
        if not doc_count:
            error_msg = "Білім қоры таңдалмаған немесе бос."
            yield f"0:{json.dumps(error_msg)}\n"
            yield _finish_event("stop")
            bot_message.content = error_msg
            db.commit()
            return

        # Build deterministic tools from DB
        tools = create_tools(db=db, knowledge_base_ids=knowledge_base_ids)
        turn_log.add_event(
            "tools.build",
            "Deterministic tools prepared",
            tool_count=len(tools),
        )

        # Get LLM with tools bound (from cache)
        _llm_key = (settings.CHAT_PROVIDER, 0.0, True)
        llm = _llm_cache[_llm_key]
        llm_with_tools = llm.bind_tools(tools)
        turn_log.add_event(
            "llm.bind",
            "Bound tools to chat model",
            provider=settings.CHAT_PROVIDER,
            tool_bound=True,
        )

        # Build chat history from DB messages
        chat_history: List = []
        for i, msg in enumerate(messages["messages"]):
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
                # Backward compat: strip old __LLM_RESPONSE__ format
                if "__LLM_RESPONSE__" in content:
                    content = content.split("__LLM_RESPONSE__")[-1]
                chat_history.append(AIMessage(content=content))

        # ═══ Stream the agent turn ═══
        full_response = ""

        async for item in run_turn(
            question=query,
            chat_history=chat_history,
            chat_id=chat_id,
            llm_with_tools=llm_with_tools,
            tools=tools,
            turn_log=turn_log,
        ):
            if isinstance(item, TurnLog):
                turn_log = item
            elif isinstance(item, dict) and item.get("type") == "step":
                # Stream step events as Vercel AI data annotations
                yield f"8:[{json.dumps(item, ensure_ascii=False)}]\n"
            else:
                # Text token
                yield f"0:{json.dumps(item)}\n"
                full_response += item

        if turn_log:
            turn_log.pipeline_total_ms = (time.perf_counter() - pipeline_start) * 1000
            turn_log.add_event(
                "turn.finish",
                "Chat turn completed",
                iterations=turn_log.iterations,
                tool_calls=turn_log.tool_calls,
                tool_batches=len({item.batch_id for item in turn_log.tool_executions}),
                total_ms=round(turn_log.pipeline_total_ms, 2),
            )
            logger.info("\n%s", turn_log.format_backend_report(chat_id, status="ok"))

        yield _finish_event("stop")

        bot_message.content = full_response
        db.commit()

    except Exception as e:
        turn_log.add_event(
            "turn.error",
            "Chat turn failed",
            error=str(e),
        )
        logger.error("\n%s", turn_log.format_backend_report(chat_id, status="error"))
        logger.exception("Error generating response for chat_id=%s: %s", chat_id, e)
        yield f"0:{json.dumps(_SYSTEM_ERROR_KZ)}\n"
        yield _finish_event("error")
        if "bot_message" in locals():
            bot_message.content = _SYSTEM_ERROR_KZ
            db.commit()
    finally:
        db.close()
