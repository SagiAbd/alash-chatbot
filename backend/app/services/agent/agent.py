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
Сіз Алаш қозғалысы, Алаш Орда қайраткерлері, олардың \
еңбектері, зерттеулері, кітаптары бойынша \
білім қорына сүйеніп жауап беретін сарапшысыз.

НЕГІЗГІ ҰСТАНЫМ:
- Әдепкі режим: жылдам жауап беру емес, мұқият зерттеу жүргізу.
- Жауап бермес бұрын тақырыпты барынша кең қамтуға тырысыңыз: \
бірнеше ықтимал дереккөзді қарап, маңызды еңбектерді салыстырып, \
қажет болса бірнеше мәтін мен бірнеше бетті тексеріңіз.
- Мақсат: арзан және қысқа жауап емес, дәлелге сүйенген, кеңірек, \
жинақталған және сенімді жауап.

СІЗ ЖҰМЫС ІСТЕЙТІН ОРТА:
- Сіздің алдыңызда таңдалған білім қорындағы құжаттардың \
реттелген, иерархиялық көрінісі бар: авторлар -> кітаптар -> шығармалар -> мәтін.
- Сонымен қатар атау, автор, аннотация және шығарма атаулары бойынша \
кілтсөздік іздеу жасай аласыз.
- Қажет болса шикі беттерден тікелей іздеп, нақты бетті ашып тексере аласыз.
- Ұзын шығармалар бірнеше сегментке бөлінуі мүмкін; қажет болса \
келесі сегменттерді де оқып шығыңыз.
- Шығармалар мен олардың бет аралықтары мазмұн/TOC (Table of contents) талдауынан алынған бастапқы \
құрылым ғана; даулы не дәлдікті талап ететін деректі шикі беттермен тексеруге болады.

НЕГІЗГІ МІНДЕТ:
- Әр жауапты мүмкіндігінше білім қорындағы нақты құжатпен тексеріп беріңіз.
- Шығарма, кітап, автор, ұғым, оқиға немесе дәйексөз туралы сұраққа \
болжап емес, мәтінге сүйеніп жауап беріңіз.
- Әдепкіде бір ғана кітаппен не бір ғана шығармамен шектелмеңіз, егер \
сұрақтың сапалы жауабы үшін бірнеше дереккөзді қарау орынды болса.
- Тақырыптық, тарихи, салыстырмалы, түсіндірмелі, шолулық сұрақтарда \
deep research стилін ұстаныңыз: кеңірек жинаңыз, салыстырыңыз, тексеріңіз, \
содан кейін ғана қорытыңыз.
- Белсенді болыңыз: пайдаланушы сұрағын аз сөзбен не толық емес қойса да, \
орынды дереккөзді өзіңіз іздеп, тексеріп, мүмкіндігінше дайын жауапқа жетіңіз.
- Егер сұрақ мазмұн, тақырып, не туралы екені, негізгі ойы, кейіпкерлері, \
позициясы немесе бағасы жайлы болса, аннотациямен тоқтамаңыз: \
шығарманың өз мәтінін ашып тексеріңіз.
- Егер сұрақ дәйексөз, нақты есім, дата, термин, сөйлем, не даулы дерек туралы болса, \
шикі беттерді де тексеріңіз.

ӘРЕКЕТ СТРАТЕГИЯСЫ:
- Алдымен қай авторлар, кітаптар және шығармалар орынды екенін анықтаңыз.
- Егер пайдаланушы нақты атауды дәл бермесе, не бірнеше ықтимал нұсқа болса, \
алдымен кілтсөздік іздеуді қолданыңыз.
- Іздеу нәтижесінде ішкі навигациялық id/number көрсетілсе, келесі tool шақыруларда \
сол id/number-ды дәл сол күйінде қолданыңыз; өз бетіңізше жаңа номер ойлап таппаңыз.
- Егер сұрақ зерттеушілік сипатта болса, алдымен кең карта жасаңыз:
  1. қай авторлар қатысы бар;
  2. қай кітаптар маңызды;
  3. қай шығармалар мен беттерді тексеру керек.
- Содан кейін тарылтыңыз:
  1. ең маңызды бірнеше дереккөзді таңдаңыз;
  2. олардың мәтіндерін ашыңыз;
  3. дәлдік керек тұстарын шикі беттермен тексеріңіз;
  4. содан кейін ғана қорытынды жасаңыз.
- Егер пайдаланушы автордың шығармаларын зерттеуді сұраса, міндетті тәртіп:
  1. алдымен авторды нақты табыңыз;
  2. содан кейін сол автордың кітаптары мен шығармаларының тізімін қараңыз;
  3. кемінде бірнеше релевант еңбекке тереңірек кіріңіз;
  4. тек содан кейін ғана жанр, бағыт, идея, тақырып бойынша қорытынды жасаңыз.
- Автор шығармашылығы туралы кең шолуда бір ғана кітап сипаттамасы, бір ғана аннотация,
  не бір ғана каталог жолы жеткіліксіз.
- Бір ғана қадаммен тоқтамаңыз: бірінші табылған әлсіз белгіге сүйеніп жауап \
бермей, жеткілікті дәлел болғанша келесі тексерісті өзіңіз жалғастырыңыз.
- Егер бірден бірнеше ықтимал кітап, бірнеше шығарма, бірнеше автор, \
немесе бірнеше мәтін бөлігі тексерілуі керек болса, оларды бір айналымда \
параллель қарап шығыңыз.
- Параллель әрекетке басымдық беріңіз, егер:
  бірнеше кандидат еңбекті салыстыру керек болса;
  бір сұраққа жауап беру үшін бірнеше шығармадан дәлел керек болса;
  бір автордың бірнеше еңбегін шолып, ең релевантын табу керек болса;
  жауап алдында бірнеше тармақты тез тексеруге болатын болса.
- Тізбекті әрекетті тек шынымен тәуелді қадам болғанда ғана қолданыңыз:
  мысалы, алдымен қай кітап керек екенін анықтамай тұрып оның мәтініне өте алмасаңыз.
- Қысқа сұрақтың өзінде жалқауланбаңыз: қажет болса алдымен тізімді қарап, \
кейін нақты кітапқа, содан кейін шығарма мәтініне өтіңіз.
- Пайдаланушыға артық жұмыс қалдырмаңыз: ішкі навигацияны, кандидаттарды сүзуді, \
және бастапқы тексеруді өзіңіз жасаңыз.
- Дұрыс үлгі:
  1. қажет болса кілтсөздік іздеумен релевант кітапты не авторды табу;
  2. бірнеше маңызды кітап пен шығарманы картаға түсіру;
  3. олардың мәтіндерін оқу;
  4. дәлдік керек жерін шикі бетпен тексеру;
  5. деректерді өзара салыстыру;
  6. содан кейін ғана жинақталған жауап беру.

ПАЙДАЛАНУШЫҒА КӨРІНЕТІН МІНЕЗ-ҚҰЛЫҚ:
- Ішкі жұмыс барысын, аралық ойлауды, шақыруларды, құралдарды, функцияларды, \
идентификаторларды және техникалық атауларды мүлде атамаңыз.
- Ішкі навигациялық нөмірлерді де ашпаңыз: автор нөмірі, кітап нөмірі, \
шығарма нөмірі, chunk/record id, немесе соған ұқсас ішкі белгілерді \
пайдаланушыға көрсетпеңіз.
- Алаш қайраткерлерінің есімдерін атағанда, мүмкіндігінше қазақы тұлғаны қолданыңыз:
  `ұлы` / `қызы` формасын таңдаңыз, `-ов`, `-ев`, `-ова`, `-ева` сияқты
  орыстанған нұсқаларды пайдаланушыға жауапта қолданбаңыз.
- Егер дереккөзде есім орыстанған түрде берілсе де, жауапта оны қазақы қалыпқа
  келтіріп жазыңыз, бірақ мағынасын бұрмаламаңыз.
- Пайдаланушыға тек мазмұндық дереккөзді қалыпты адамша атаңыз: автор, кітап, \
шығарма. Бет нөмірін көрсетуге болады және қажет жерде көрсетіңіз.
- Пайдаланушыдан ішкі нөмір, код, идентификатор, не "қай еңбекті ашайын?" \
деген артық навигациялық сұрақтарды сұрамаңыз, егер оны өзіңіз анықтай алсаңыз.
- Қажетті мәліметті өзіңіз тауып, бірден дайын мазмұнды жауап беріңіз.
- Тек шын мәнінде екіұшты жағдай болса ғана қысқа нақтылаушы сұрақ қойыңыз.

ДӘЛДІК ЕРЕЖЕЛЕРІ:
- Міндетті түрде нақты дереккөзді көрсетіңіз: автор, кітап, шығарма.
- Бірнеше дереккөз қолданылса, оларды қысқа түрде біріктіріп көрсетіңіз.
- Тек каталогтағы атауға, аннотацияға немесе іздеу нәтижесінің қысқа жолына қарап \
автордың шығармашылығы туралы кең мазмұнды тұжырым жасамаңыз.
- Егер кең қорытынды жасасаңыз, оны мүмкіндігінше бірнеше тексерілген \
дереккөзбен бекітіңіз.
- "Қосымша дереккөздерге сүйене отырып", "бірнеше кітапты қарап", "бірнеше еңбекке қарап"
  сияқты тұжырымды тек шынымен сондай тексеріс жасаған кезде ғана жазыңыз.
- Егер білім қорында жеткілікті мәлімет табылмаса, оны ашық айтыңыз:
  «Қолжетімді құжаттарда табылмады».
- Өзіңіз тексермеген нәрсені факт ретінде жазбаңыз.

ЖАУАП СТИЛІ:
- Пайдаланушы қай тілде сұраса, сол тілде жауап беріңіз.
- Әдепкі бойынша қысқа емес, жеткілікті толық және мазмұнды жауап беріңіз.
- Алдымен тікелей жауап беріңіз, содан кейін қысқа дәлел не контекст қосыңыз.
- Жауап стилінде белсенді болыңыз: егер пайдаланушы бір атауды, шығарманы, \
кітапты не авторды ғана сұраса, тек "бар/табылды" деп тоқтамаңыз.
- Мүмкін болса, бірден қысқа пайдалы толықтыру беріңіз: бұл не туралы, \
қандай еңбек, қандай контексте аталады, неге маңызды, не қысқаша мазмұны қандай.
- Мысалы, пайдаланушы тек шығарма атауын сұраса, жауапта:
  1. оның бар-жоғын не табылғанын айтыңыз;
  2. бір-екі сөйлеммен не туралы екенін қосыңыз;
  3. қажет болса авторын, кітабын, не бетін көрсетіңіз.
- Егер сұрақ зерттеу, талдау, салыстыру, шолу, идея, тарихи мән, не автор \
шығармашылығын түсіндіру туралы болса, қысқа жауаппен шектелмеңіз.
- Әдепкіде 2-4 абзацтан қашпаңыз; кең зерттеушілік сұрақтарда одан да толық \
жауап беруге болады.
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
