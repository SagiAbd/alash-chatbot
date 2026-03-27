"""Agent nodes for LangGraph — Alash chatbot.

Nodes:
  1. call_model_node: LLM with document-browsing tools bound. Decides
     which tools to call or generates a final answer.
  2. custom_tool_node: Executes tool calls from the LLM.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Literal

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig

from app.services.agent.state import AgentState, TurnLog

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Сіз Алаш қозғалысының, оның мүшелерінің (Алаш Орда), \
олардың зерттеулерінің, кітаптарының және тарихи \
маңызының сарапшысысыз.

Сізде білім қорындағы құжаттарды иерархиялық түрде \
шолуға арналған құралдар бар:

ЖҰМЫС ТӘРТІБІ:
1. Алдымен get_authors_and_books() шақырыңыз — \
қандай авторлар мен кітаптар бар екенін біліңіз.
2. Қажетті кітап туралы толық ақпарат алу үшін \
get_book_details(book_number) шақырыңыз.
3. Автордың барлық шығармаларын көру үшін \
get_author_works(author_number) шақырыңыз.
4. Нақты шығарманың мәтінін оқу үшін \
get_work_content(work_number) шақырыңыз.
   Ұзын шығармалар сегменттерге бөлінеді — келесі \
сегментті page_offset арқылы оқыңыз.
5. Бірнеше құралды бір уақытта шақыра аласыз \
(параллель). Мысалы: бірнеше шығарманы бірден оқу.

ЕРЕЖЕЛЕР:
- Жауап бермес бұрын міндетті түрде құралдар \
арқылы құжаттарды тексеріңіз.
- Дереккөзді нақты көрсетіңіз: автор аты, кітап \
атауы, шығарма атауы.
- Егер білім қорында ақпарат жоқ болса: \
«Қолжетімді құжаттарда табылмады» деңіз.
- Жауабыңыз кәсіби, ғылыми стильде жазылсын.
- Сұрақ тілінде жауап беріңіз (қазақша/орысша).

ЖАУАП СТИЛІ:
- Әдепкі бойынша қысқа, нақты жауап беріңіз.
- Ұзақ талдау, толық мәтін немесе кеңейтілген \
жауап тек пайдаланушы нақты сұраған жағдайда ғана.
- Мысалы: "толық талдау жаса", "кеңірек жаз", \
"барлығын көрсет" деген сұрақтарға — толық жауап.
- Қарапайым сұрақтарға 2-4 абзац жеткілікті.
"""


def _trim_tool_history(
    messages: List[BaseMessage], keep_turns: int = 1
) -> List[BaseMessage]:
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
    """Call the LLM with document-browsing tools bound.

    LLM either calls tools to navigate documents or generates the final answer.
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
    """Execute tool calls from the last AIMessage (parallel)."""
    last_message = state["messages"][-1]
    turn_log = state.get("turn_log") or TurnLog()
    tools = config["configurable"]["tools"]
    tool_map = {t.name: t for t in tools}

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {"messages": [], "turn_log": turn_log}

    async def _run_one(tc: dict) -> ToolMessage:
        name = tc["name"]
        args = tc["args"]
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

        return ToolMessage(
            content=str(output),
            tool_call_id=tc["id"],
            name=name,
        )

    results = await asyncio.gather(*[_run_one(tc) for tc in last_message.tool_calls])

    return {
        "messages": list(results),
        "turn_log": turn_log,
    }


def tools_condition(state: AgentState) -> Literal["tools", "__end__"]:
    """Route to tools if the LLM made tool calls, otherwise end."""
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "__end__"
