"""Agent nodes for LangGraph — Alash chatbot.

Nodes:
  1. call_model_node: LLM with document-browsing tools bound. Decides
     which tools to call or generates a final answer.
  2. custom_tool_node: Executes tool calls from the LLM.
"""

import asyncio
import json
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

from app.core.config import settings
from app.services.agent.state import AgentState, TurnLog

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Сіз Алаш қозғалысы мен Алаш Орда қайраткерлерінің еңбектері бойынша \
білім қорына сүйеніп жауап беретін сарапшысыз.

ЖҰМЫС ОРТАСЫ:
Білім қорында авторлар → кітаптар → шығармалар → мәтін иерархиясы бар.
Қолжетімді инструменттер:
- `search_catalog`: атау, автор, аннотация бойынша кілтсөздік іздеу.
- `get_authors_and_books`: барлық авторлар мен кітаптар тізімі.
- `get_book_details`: кітаптың шығармалар тізімі мен аннотациясы.
- `get_author_works`: автордың барлық кітаптары мен шығармалары.
- `get_work_content`: шығарма мәтіні (сегменттеп беріледі).
- `search_pages`: шикі беттерден іздеу немесе белгілі бетті оқу \
(full_content=true берсе — толық бет мәтіні; query бос болса — ауқымдағы барлық беттер).
- `search_terms`: Алаш дәуірі ғылыми терминдер глоссарийі (қосымша контекст).

МАҢЫЗДЫ — get_work_content туралы:
Шығарма мәтіні TOC негізіндегі бет аралығынан жиналады; шеттерінде padding ретінде \
көрші беттер кіруі мүмкін. Дәйексөз, есім, күн, термин, даулы дерек болса — \
сол үзіндіні `search_pages` арқылы нақты беттен тексеріңіз.

МАҢЫЗДЫ — АВТОР ЕСІМДЕРІ:
Білім қорындағы атаулар орыстандырылған түрде сақталуы мүмкін \
(мысалы, «Байтурсынов», «Дулатов»). Пайдаланушы қазақша нұсқа берсе \
(«Байтұрсынұлы»), іздеуді екі нұсқамен де қайталап көріңіз. \
Жауапта есімді әрдайым қазақы тұлғада беріңіз (ұлы/қызы формасы).

ІЗДЕУ СТРАТЕГИЯСЫ:
1. Қатысы бар авторлар мен кітаптарды анықтаңыз \
(`search_catalog` немесе `get_authors_and_books`).
2. Нақты кітап/шығарма белгілі болса — тікелей мазмұнын ашыңыз.
3. Белгісіз болса: catalog іздеу → `book_details` немесе `author_works`.
4. Маңызды шығармалардың мәтінін оқыңыз; дәлдік керек жерлерде \
шикі беттермен тексеріңіз (`search_pages`).
5. Бірнеше дереккөз керек болса — бір айналымда параллель шақырыңыз.
6. Іздеу нәтижесіндегі ішкі id/number-ды өзгертпей қолданыңыз.
7. Аннотациямен немесе бір ғана каталог жолымен шектелмеңіз — мәтінге кіріңіз.

ТОҚТАТУ ЕРЕЖЕСІ:
- Әдепкіде мақсат — мұқият, дәлелге сүйенген жауап, бірақ шексіз іздеу емес.
- 3–4 іздеу айналымынан кейін релевант нәтиже табылмаса — одан әрі іздеуді \
тоқтатып, «Қолжетімді құжаттарда табылмады» деп нақты жазыңыз.
- Жеткілікті дәлел жиналса — тоқтап, жауап беріңіз; артық тексерістен қашыңыз.
- Болжаммен немесе тексерілмеген дерекпен жауап бермеңіз.

СТИЛЬДІК СҰРАУ (мысалы, «Алаш стилінде», «пәленшенің үнінде»):
- Стиль иесі анық болмаса — қысқа нақтылау сұрағын қойыңыз.
- Анық болса — жауапқа дейін сол автордың 2–3 шығармасын оқып шығыңыз.
- Дереккөздің сөйлемін сол күйінде көшірмеңіз; тек үнін, ырғағын, лексикасын \
бейімдеңіз.
- Жеткілікті мәтін табылмаса — мұны ашық айтып, Алаш дәуіріне жуық әдеби \
мәнермен ғана жауап беретініңізді көрсетіңіз.

ПАЙДАЛАНУШЫҒА МІНЕЗ-ҚҰЛЫҚ:
- Ішкі нөмірлерді, tool атауларын, chunk/record id-лерді ешқашан көрсетпеңіз.
- Сілтемеде тек адамға түсінікті атаулар: автор, кітап, шығарма, бет нөмірі.
- Тек шынымен екіұшты жағдай болса ғана қысқа нақтылаушы сұрақ қойыңыз; \
қалған жағдайда өзіңіз тауып, дайын жауап беріңіз.

ДӘЛДІК:
- Дереккөзден үзінді — сөзбе-сөз, редакциясыз; автор/кітап/шығарма атаңыз.
- Каталог атауы немесе аннотация ғана негізінде кең тұжырым жасамаңыз.
- Кең қорытынды — бірнеше тексерілген дереккөзбен бекітіңіз.
- Тексермеген нәрсені факт ретінде жазбаңыз.

ЖАУАП СТИЛІ:
- Пайдаланушы тілінде жауап беріңіз.
- Қазақша: таза әдеби тіл; калькадан, орысша құрылымнан аулақ болыңыз.
- Тікелей жауаптан бастап, қысқа дәлел мен контекст қосыңыз.
- Әдепкіде толық, мазмұнды жауап (2–4 абзац); зерттеушілік сұрақтарда одан артық.
- Қысқа сұраққа «бар/табылды» деп тоқтамаңыз — бір-екі сөйлеммен не туралы \
екенін, авторын, кітабын, қажет болса бетін қосыңыз.
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


def _message_role(message: BaseMessage) -> str:
    """Return a stable human-readable role for a LangChain message."""
    if isinstance(message, SystemMessage):
        return "system"
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, ToolMessage):
        return "tool"
    if isinstance(message, AIMessage):
        return "assistant"
    return message.__class__.__name__.lower()


def _message_content(message: BaseMessage) -> Any:
    """Extract message content in a loggable form."""
    content = message.content
    if isinstance(content, list):
        normalized: List[Any] = []
        for block in content:
            if isinstance(block, dict):
                normalized.append(block)
            else:
                normalized.append(str(block))
        return normalized
    return content


def _serialize_messages(messages: List[BaseMessage]) -> str:
    """Serialize the final prompt payload for verbose logging."""
    payload: List[Dict[str, Any]] = []
    for message in messages:
        item: Dict[str, Any] = {
            "role": _message_role(message),
            "content": _message_content(message),
        }
        if isinstance(message, AIMessage) and getattr(message, "tool_calls", None):
            item["tool_calls"] = message.tool_calls
        if isinstance(message, ToolMessage):
            item["tool_call_id"] = message.tool_call_id
            item["name"] = getattr(message, "name", "")
        payload.append(item)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _serialize_response(response: AIMessage) -> str:
    """Serialize the raw model response for verbose logging."""
    payload: Dict[str, Any] = {
        "content": _message_content(response),
        "tool_calls": getattr(response, "tool_calls", []) or [],
        "response_metadata": getattr(response, "response_metadata", {}) or {},
        "usage_metadata": getattr(response, "usage_metadata", {}) or {},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


async def call_model_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Call the LLM with document-browsing tools bound.

    LLM either calls tools to navigate documents or generates the final answer.
    """
    turn_log = state.get("turn_log") or TurnLog()
    llm_with_tools = config["configurable"]["llm_with_tools"]

    messages = _trim_tool_history(state["messages"])
    full_messages = [SystemMessage(content=_SYSTEM_PROMPT)] + messages

    if settings.AGENT_VERBOSE:
        logger.info("LLM final prompt payload:\n%s", _serialize_messages(full_messages))

    turn_log.add_event(
        "llm.call.start",
        "Calling chat model",
        iteration=turn_log.iterations + 1,
        message_count=len(full_messages),
    )

    t0 = time.perf_counter()
    response = await llm_with_tools.ainvoke(full_messages)
    elapsed = (time.perf_counter() - t0) * 1000

    if settings.AGENT_VERBOSE:
        logger.info("LLM raw response payload:\n%s", _serialize_response(response))

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
