"""LangGraph graph for the Alash chatbot.

Flow:
  START → agent → tools (if tool_calls) → agent → ... → END

Compiled with MemorySaver (in-memory checkpointer — resets on restart).
Call init_graph() at application startup.
"""

import logging
from typing import AsyncGenerator, List

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.services.agent.state import AgentState, TurnLog
from app.services.agent.agent import call_model_node, custom_tool_node, tools_condition

logger = logging.getLogger(__name__)

# ─── Graph Construction ─────────────────────────────────────────────

_workflow = StateGraph(AgentState)
_workflow.add_node("agent", call_model_node)
_workflow.add_node("tools", custom_tool_node)
_workflow.set_entry_point("agent")
_workflow.add_conditional_edges(
    "agent",
    tools_condition,
    {"tools": "tools", "__end__": END},
)
_workflow.add_edge("tools", "agent")

# ─── Compiled graph (lazy init) ─────────────────────────────────────

_app = None


def init_graph() -> None:
    """Compile the graph with a MemorySaver checkpointer.
    Call once during application startup.
    """
    global _app
    checkpointer = MemorySaver()
    _app = _workflow.compile(checkpointer=checkpointer)
    logger.info("LangGraph compiled with MemorySaver checkpointer")


def get_graph_app():
    if _app is None:
        raise RuntimeError("LangGraph app not initialized — call init_graph() at startup.")
    return _app


# ─── Entry Point ─────────────────────────────────────────────────────

def _get_chunk_content(chunk) -> str:
    """Extract text from a streaming AIMessageChunk."""
    content = chunk.content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return content if isinstance(content, str) else ""


async def run_turn(
    question: str,
    chat_history: List,
    chat_id: int,
    llm_with_tools,
    tools: List,
) -> AsyncGenerator:
    """Stream a single conversation turn via LangGraph.

    Yields str tokens for the final response, then yields a TurnLog as
    the last item.
    """
    graph_app = get_graph_app()

    config = {
        "configurable": {
            "thread_id": str(chat_id),
            "llm_with_tools": llm_with_tools,
            "tools": tools,
        },
        "recursion_limit": 10,
    }

    # Check for existing checkpoint
    checkpoint_snapshot = await graph_app.aget_state(config)
    has_checkpoint = bool(
        checkpoint_snapshot
        and checkpoint_snapshot.values
        and checkpoint_snapshot.values.get("messages")
    )

    if has_checkpoint:
        initial_state: AgentState = {
            "messages": [HumanMessage(content=question)],
            "question": question,
            "turn_log": TurnLog(),
        }
    else:
        initial_state: AgentState = {
            "messages": chat_history + [HumanMessage(content=question)],
            "question": question,
            "turn_log": TurnLog(),
        }

    turn_log = TurnLog()
    async for event in graph_app.astream_events(initial_state, config, version="v2"):
        if event["event"] == "on_chat_model_stream":
            node = event.get("metadata", {}).get("langgraph_node", "")
            if node == "agent":
                chunk = event["data"]["chunk"]
                content = _get_chunk_content(chunk)
                if content and not chunk.tool_call_chunks:
                    yield content
        elif event["event"] == "on_chain_end":
            output = event["data"].get("output") or {}
            if isinstance(output, dict) and "turn_log" in output:
                turn_log = output["turn_log"]

    yield turn_log
