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

Сіз білім қорындағы құжаттарды өзіңіз қарап, \
қажетті деректі өзіңіз табасыз.

ЖҰМЫС ТӘРТІБІ:
- Пайдаланушы тарихи не әдеби сұрақ қойса, \
алдымен міндетті түрде білім қорындағы құжаттарды тексеріңіз.
- Қажет болса, бірнеше дереккөзді бірден қарап, \
сосын ғана қорытынды жауап беріңіз.
- Шығарма, кітап, автор немесе тақырып туралы сұралса, \
жалқауланбай нақты мәтінге дейін барып тексеріңіз.
- Қысқа сұрақтың өзіне де құжатты ашып тексермей болжап жауап бермеңіз.

ЕРЕЖЕЛЕР:
- Пайдаланушыға ішкі жұмыс барысын айтпаңыз.
- Құрал, функция, шақыру, нөмір, идентификатор, \
`work_number`, `book_number` сияқты ішкі атауларды \
ешқашан атамаңыз.
- Пайдаланушыдан ішкі нөмірді, идентификаторды, \
не "мәтінді ашуға рұқсат" сияқты артық қадамдарды сұрамаңыз.
- Қажетті мәліметті өзіңіз тауып, мүмкін болса \
бірден мазмұнды жауап беріңіз.
- Тек шын мәнінде айқынсыздық болса ғана нақтылаушы сұрақ қойыңыз.
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

    turn_log.add_event(
        "llm.call.start",
        "Calling chat model",
        iteration=turn_log.iterations + 1,
        message_count=len(full_messages),
    )

    t0 = time.perf_counter()
    response = await llm_with_tools.ainvoke(full_messages)
    elapsed = (time.perf_counter() - t0) * 1000

    turn_log.iterations += 1
    turn_log.timing_ms[f"LLM call {turn_log.iterations}"] = elapsed
    turn_log.add_event(
        "llm.call.finish",
        "Chat model responded",
        iteration=turn_log.iterations,
        duration_ms=round(elapsed, 2),
        tool_call_count=len(getattr(response, "tool_calls", []) or []),
    )

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

    batch_id = turn_log.register_tool_batch(last_message.tool_calls)
    parallel = len(last_message.tool_calls) > 1
    turn_log.add_event(
        "tools.batch.start",
        "Starting tool batch",
        batch_id=batch_id,
        tool_count=len(last_message.tool_calls),
        parallel=parallel,
        tools=[tc["name"] for tc in last_message.tool_calls],
    )

    async def _run_one(tc: dict) -> ToolMessage:
        name = tc["name"]
        args = tc["args"]
        turn_log.tool_calls.append(name)
        turn_log.mark_tool_started(tc["id"])
        turn_log.add_event(
            "tool.start",
            "Executing tool",
            batch_id=batch_id,
            tool=name,
            parallel=parallel,
            args=args,
        )

        t0 = time.perf_counter()
        status = "success"
        if name in tool_map:
            try:
                output = await tool_map[name].ainvoke(args)
            except Exception as e:
                output = f"Қате: {e}"
                status = "error"
        else:
            output = f"Белгісіз құрал: {name}"
            status = "missing"

        elapsed = (time.perf_counter() - t0) * 1000
        turn_log.timing_ms[f"Tool: {name}"] = elapsed
        turn_log.tool_results[name] = str(output)[:500]
        turn_log.mark_tool_finished(
            tc["id"],
            duration_ms=elapsed,
            status=status,
            result_preview=str(output)[:200],
        )
        turn_log.add_event(
            "tool.finish",
            "Tool finished",
            batch_id=batch_id,
            tool=name,
            status=status,
            duration_ms=round(elapsed, 2),
        )

        return ToolMessage(
            content=str(output),
            tool_call_id=tc["id"],
            name=name,
        )

    results = await asyncio.gather(*[_run_one(tc) for tc in last_message.tool_calls])
    turn_log.add_event(
        "tools.batch.finish",
        "Tool batch completed",
        batch_id=batch_id,
        tool_count=len(results),
        parallel=parallel,
    )

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
