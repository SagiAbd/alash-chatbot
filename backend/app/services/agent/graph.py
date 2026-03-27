"""LangGraph graph for the Alash chatbot.

Flow:
  START -> agent -> tools (if tool_calls) -> agent -> ... -> END

Compiled with MemorySaver (in-memory checkpointer -- resets on restart).
Call init_graph() at application startup.
"""

import json
import logging
from typing import AsyncGenerator, Dict, List

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.services.agent.agent import call_model_node, custom_tool_node, tools_condition
from app.services.agent.state import AgentState, TurnLog

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
        raise RuntimeError(
            "LangGraph app not initialized -- call init_graph() at startup."
        )
    return _app


# ─── Step event helpers ──────────────────────────────────────────────


def _step_event(step: str, **kwargs: object) -> Dict:
    """Build a step event dict for streaming to the frontend."""
    return {"type": "step", "step": step, **kwargs}


def _summarize_tool_result(output: str, max_len: int = 120) -> str:
    """Create a short summary of a tool result for the UI."""
    lines = output.strip().splitlines()
    if len(lines) <= 3:
        summary = output.strip()
    else:
        summary = "\n".join(lines[:3]) + f"\n... ({len(lines)} жол)"
    if len(summary) > max_len:
        return summary[:max_len] + "..."
    return summary


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

    Yields:
        dict: Step events (type="step") for agent reasoning visibility.
        str: Text tokens for the final response.
        TurnLog: As the last item, with timing/debug info.
    """
    graph_app = get_graph_app()

    config = {
        "configurable": {
            "thread_id": str(chat_id),
            "llm_with_tools": llm_with_tools,
            "tools": tools,
        },
        "recursion_limit": 30,
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
    agent_iteration = 0
    pending_tool_calls: Dict[str, str] = {}  # tool_call_id -> tool_name

    async for event in graph_app.astream_events(initial_state, config, version="v2"):
        kind = event["event"]
        node = event.get("metadata", {}).get("langgraph_node", "")

        # ── Agent starts thinking ────────────────────────────────
        if kind == "on_chain_start" and node == "agent":
            agent_iteration += 1
            if agent_iteration == 1:
                yield _step_event("thinking", content="Сұрақты талдау...")
            else:
                yield _step_event("thinking", content="Нәтижелерді талдау...")

        # ── Tool call detected from LLM output ──────────────────
        if kind == "on_chat_model_end" and node == "agent":
            output = event["data"].get("output")
            if output and hasattr(output, "tool_calls") and output.tool_calls:
                for tc in output.tool_calls:
                    pending_tool_calls[tc["id"]] = tc["name"]
                    args_str = (
                        json.dumps(tc["args"], ensure_ascii=False) if tc["args"] else ""
                    )
                    yield _step_event(
                        "tool_call",
                        tool=tc["name"],
                        args=args_str,
                    )

        # ── Tool execution completes ─────────────────────────────
        if kind == "on_tool_end":
            tool_name = event.get("name", "")
            output = event["data"].get("output", "")
            output_str = str(output)
            summary = _summarize_tool_result(output_str)
            yield _step_event(
                "tool_result",
                tool=tool_name,
                summary=summary,
            )

        # ── Stream final answer tokens ───────────────────────────
        if kind == "on_chat_model_stream" and node == "agent":
            chunk = event["data"]["chunk"]
            content = _get_chunk_content(chunk)
            if content and not chunk.tool_call_chunks:
                yield content

        # ── Capture turn log ─────────────────────────────────────
        if kind == "on_chain_end":
            output = event["data"].get("output") or {}
            if isinstance(output, dict) and "turn_log" in output:
                turn_log = output["turn_log"]

    yield turn_log
