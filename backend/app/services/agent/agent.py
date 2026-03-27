"""Agent nodes for LangGraph — Alash chatbot.

Nodes:
  1. call_model_node: LLM with search_kb tool bound. Decides whether to
     call the tool or generate a final answer.
  2. custom_tool_node: Executes tool calls from the LLM.
"""

import time
import logging
from typing import Dict, Any, Literal, List

from langchain_core.messages import SystemMessage, AIMessage, ToolMessage, HumanMessage, BaseMessage
from langchain_core.runnables import RunnableConfig

from app.services.agent.state import AgentState, TurnLog
from app.core.config import settings

logger = logging.getLogger(__name__)

# System prompt in Kazakh
_SYSTEM_PROMPT = """Сіз Алаш қозғалысының, оның мүшелерінің (Алаш Орда), олардың зерттеулерінің, кітаптарының және тарихи маңызының сарапшысысыз.

МІНДЕТТІ ЕРЕЖЕЛЕР:
1. Жауап бермес бұрын search_kb құралын әрқашан шақыру қажет. Бұл міндетті.
2. Іздеу сұрағын пайдаланушының сұрағынан кеңейтіңіз: синонимдер, байланысты терминдер және балама тіркестер қосыңыз.
3. Іздеу нәтижелерін пайдаланып, [1], [2] пішімінде дереккөз көрсетіңіз.
4. Егер білім қорында жеткілікті ақпарат болмаса: «Қолжетімді Алаш деректерінде бұл туралы ақпарат жоқ» деңіз.
5. Жауабыңыз кәсіби, ғылыми стильде жазылуы керек.
6. Жауабыңызды сұрақ тілінде жазыңыз (қазақша немесе орысша).
"""

def _trim_tool_history(messages: List[BaseMessage], keep_turns: int = 1) -> List[BaseMessage]:
    """Keep ToolMessages only for the last N completed turns to save context."""
    if keep_turns < 0 or not messages:
        return messages

    human_positions = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    if not human_positions:
        return messages

    keep_from = (
        human_positions[-(keep_turns + 1)]
        if keep_turns + 1 <= len(human_positions)
        else 0
    )

    filtered = []
    for i, msg in enumerate(messages):
        if i < keep_from:
            if isinstance(msg, HumanMessage):
                filtered.append(msg)
            elif isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                filtered.append(msg)
        else:
            filtered.append(msg)
    return filtered


async def call_model_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Call the LLM with tools bound.

    LLM either:
    - Calls search_kb (tool call) to retrieve context, OR
    - Generates the final answer directly
    """
    turn_log = state.get("turn_log") or TurnLog()
    llm_with_tools = config["configurable"]["llm_with_tools"]

    messages = _trim_tool_history(state["messages"])
    full_messages = [SystemMessage(content=_SYSTEM_PROMPT)] + messages

    t0 = time.perf_counter()
    response = await llm_with_tools.ainvoke(full_messages)
    elapsed = (time.perf_counter() - t0) * 1000

    turn_log.iterations += 1
    turn_log.timing_ms[f"LLM call {turn_log.iterations}"] = elapsed

    return {
        "messages": [response],
        "turn_log": turn_log,
    }


async def custom_tool_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Execute tool calls from the last AIMessage."""
    last_message = state["messages"][-1]
    turn_log = state.get("turn_log") or TurnLog()
    tools = config["configurable"]["tools"]
    tool_map = {t.name: t for t in tools}

    results = []
    if hasattr(last_message, "tool_calls"):
        for tool_call in last_message.tool_calls:
            name = tool_call["name"]
            args = tool_call["args"]
            tool_call_id = tool_call["id"]

            turn_log.tool_calls.append(name)

            t0 = time.perf_counter()
            if name in tool_map:
                try:
                    output = await tool_map[name].ainvoke(args)
                except Exception as e:
                    output = f"Қате: {e}"
            else:
                output = f"Белгісіз құрал: {name}"

            elapsed = (time.perf_counter() - t0) * 1000
            turn_log.timing_ms[f"Tool: {name}"] = elapsed
            turn_log.tool_results[name] = str(output)[:500]

            results.append(ToolMessage(
                content=str(output),
                tool_call_id=tool_call_id,
                name=name,
            ))

    return {
        "messages": results,
        "turn_log": turn_log,
    }


def tools_condition(state: AgentState) -> Literal["tools", "__end__"]:
    """Route to tools if the LLM made tool calls, otherwise end."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "__end__"
