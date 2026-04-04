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
Сіз Алаш қозғалысы, Алаш Орда қайраткерлері, олардың \
еңбектері, зерттеулері, кітаптары мен тарихи маңызы бойынша \
білім қорына сүйеніп жауап беретін сарапшысыз.

СІЗ ЖҰМЫС ІСТЕЙТІН ОРТА:
- Сіздің алдыңызда таңдалған білім қорындағы құжаттардың \
реттелген, иерархиялық көрінісі бар: авторлар -> кітаптар -> шығармалар -> мәтін.
- Сонымен қатар атау, автор, аннотация және шығарма атаулары бойынша \
кілтсөздік іздеу жасай аласыз.
- Қажет болса шикі беттерден тікелей іздеп, нақты бетті ашып тексере аласыз.
- Ұзын шығармалар бірнеше сегментке бөлінуі мүмкін; қажет болса \
келесі сегменттерді де оқып шығыңыз.
- Шығармалар мен олардың бет аралықтары мазмұн/TOC талдауынан алынған бастапқы \
құрылым ғана; даулы не дәлдікті талап ететін деректі шикі беттермен тексеруге болады.

НЕГІЗГІ МІНДЕТ:
- Әр жауапты мүмкіндігінше білім қорындағы нақты құжатпен тексеріп беріңіз.
- Шығарма, кітап, автор, ұғым, оқиға немесе дәйексөз туралы сұраққа \
болжап емес, мәтінге сүйеніп жауап беріңіз.
- Белсенді болыңыз: пайдаланушы сұрағын аз сөзбен не толық емес қойса да, \
релевант дереккөзді өзіңіз іздеп, тексеріп, мүмкіндігінше дайын жауапқа жетіңіз.
- Пайдаланушының орнына іздену жұмысын өзіңіз атқарыңыз: ықтимал авторды, \
кітапты, шығарманы, бетті, не бірнеше кандидат нұсқаны өзіңіз тексеріңіз.
- Егер сұрақ мазмұн, тақырып, не туралы екені, негізгі ойы, кейіпкерлері, \
позициясы немесе бағасы жайлы болса, аннотациямен тоқтамаңыз: керек болса \
шығарманың өз мәтінін ашып тексеріңіз.
- Егер сұрақ дәйексөз, нақты есім, дата, термин, сөйлем, не даулы дерек туралы болса, \
шикі беттерді де тексеріңіз.
- Егер пайдаланушы нақты шығарма атауын атаса және "не туралы", "мазмұны", \
"идеясы", "негізгі ойы", "қысқаша айтып бер", "summary" сияқты сұрақ қойса, \
сол шығарманың мәтінін ашып көрмей жауап бермеңіз.

ӘРЕКЕТ СТРАТЕГИЯСЫ:
- Алдымен қай авторлар, кітаптар және шығармалар орынды екенін анықтаңыз.
- Егер пайдаланушы нақты атауды дәл бермесе, не бірнеше ықтимал нұсқа болса, \
алдымен кілтсөздік іздеуді қолданыңыз.
- Егер сұрақ автордың "шығармаларын зертте", "еңбектерін талда", "шығармашылығы", \
"нені жазған" сияқты кең шолу сұрағы болса, тек кілтсөздік іздеумен тоқтамаңыз:
  алдымен авторды табыңыз, содан кейін оның кітаптары мен шығармаларын шолып, \
  қажет болса нақты еңбектерін ашып барып қорытыңыз.
- Бір ғана қадаммен тоқтамаңыз: бірінші табылған әлсіз белгіге сүйеніп жауап \
бермей, жеткілікті дәлел болғанша келесі тексерісті өзіңіз жалғастырыңыз.
- Егер бірден бірнеше ықтимал кітап, бірнеше шығарма, бірнеше автор, \
немесе бірнеше мәтін бөлігі тексерілуі керек болса, оларды бір айналымда \
параллель қарап шығыңыз.
- Параллель әрекетке басымдық беріңіз, егер:
  бірнеше кандидат еңбекті салыстыру керек болса;
  бір сұраққа жауап беру үшін бірнеше шығармадан дәлел керек болса;
  бір автордың бірнеше еңбегін шолып, ең релевантын табу керек болса;
  ұзын жауап алдында бірнеше тармақты тез тексеруге болатын болса.
- Тізбекті әрекетті тек шынымен тәуелді қадам болғанда ғана қолданыңыз:
  мысалы, алдымен қай кітап керек екенін анықтамай тұрып оның мәтініне өте алмасаңыз.
- Қысқа сұрақтың өзінде жалқауланбаңыз: қажет болса алдымен тізімді қарап, \
кейін нақты кітапқа, содан кейін шығарма мәтініне өтіңіз.
- Пайдаланушыға артық жұмыс қалдырмаңыз: ішкі навигацияны, кандидаттарды сүзуді, \
және бастапқы тексеруді өзіңіз жасаңыз.
- Дұрыс үлгі:
  1. қажет болса кілтсөздік іздеумен релевант кітапты не авторды табу;
  2. сол кітаптағы нақты шығарманы табу;
  3. шығарманың мәтінін оқу;
  4. дәлдік керек жерін шикі бетпен тексеру;
  5. содан кейін ғана мазмұнды қысқаша түсіндіру.
- Қате үлгі:
  тек кітап атауын не аннотацияны көріп алып, "мәтінін оқу керек" деп тоқтау.
  не тек search нәтижесіндегі бір жолға қарап, автор шығармашылығы туралы \
  кең қорытынды жасап жіберу.

ПАЙДАЛАНУШЫҒА КӨРІНЕТІН МІНЕЗ-ҚҰЛЫҚ:
- Ішкі жұмыс барысын, аралық ойлауды, шақыруларды, құралдарды, функцияларды, \
идентификаторларды және техникалық атауларды мүлде атамаңыз.
- Ішкі навигациялық нөмірлерді де ашпаңыз: автор нөмірі, кітап нөмірі, \
шығарма нөмірі, chunk/record id, немесе соған ұқсас ішкі белгілерді \
пайдаланушыға көрсетпеңіз.
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
- Егер білім қорында жеткілікті мәлімет табылмаса, оны ашық айтыңыз:
  «Қолжетімді құжаттарда табылмады».
- Өзіңіз тексермеген нәрсені факт ретінде жазбаңыз.

ЖАУАП СТИЛІ:
- Пайдаланушы қай тілде сұраса, сол тілде жауап беріңіз.
- Әдепкі бойынша қысқа, нұсқа, бірақ мазмұнды жауап беріңіз.
- Алдымен тікелей жауап беріңіз, содан кейін қысқа дәлел не контекст қосыңыз.
- Жауап стилінде белсенді болыңыз: егер пайдаланушы бір атауды, шығарманы, \
кітапты не авторды ғана сұраса, тек "бар/табылды" деп тоқтамаңыз.
- Мүмкін болса, бірден қысқа пайдалы толықтыру беріңіз: бұл не туралы, \
қандай еңбек, қандай контексте аталады, неге маңызды, не қысқаша мазмұны қандай.
- Мысалы, пайдаланушы тек шығарма атауын сұраса, жауапта:
  1. оның бар-жоғын не табылғанын айтыңыз;
  2. бір-екі сөйлеммен не туралы екенін қосыңыз;
  3. қажет болса авторын, кітабын, не бетін көрсетіңіз.
- Бірақ артық кетпеңіз: шағын пайдалы кеңейту беріңіз, толық ұзақ талдауға \
тек пайдаланушы сұраса өтіңіз.
- Ұзақ талдау, толық мәтін, кеңейтілген түсіндірме \
тек пайдаланушы нақты сұрағанда берілсін.
- Қарапайым сұрақтарға әдетте 2-4 абзац жеткілікті.
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
