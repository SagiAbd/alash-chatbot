"""Agent state for the LangGraph-based Alash chatbot."""

import json
from dataclasses import dataclass, field
from typing import Annotated, Any, Dict, List, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """LangGraph state for the Alash RAG agent."""

    messages: Annotated[List[BaseMessage], add_messages]
    question: str
    turn_log: "TurnLog"


@dataclass
class TurnEvent:
    """A single ordered backend event emitted during one chat turn."""

    seq: int
    stage: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def format_backend_line(self, chat_id: int | str) -> str:
        """Render a compact backend log line."""
        details_str = " ".join(
            f"{key}={self._serialize_value(value)}"
            for key, value in self.details.items()
            if value not in (None, "", [], {})
        )
        if details_str:
            return (
                f"[chat_id={chat_id} seq={self.seq:02d} stage={self.stage}] "
                f"{self.message} | {details_str}"
            )
        return (
            f"[chat_id={chat_id} seq={self.seq:02d} stage={self.stage}] "
            f"{self.message}"
        )

    @staticmethod
    def _serialize_value(value: Any) -> str:
        """Serialize event detail values for readable logs."""
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, (list, dict, tuple)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)


@dataclass
class ToolExecutionLog:
    """Execution metadata for one tool call within a turn."""

    batch_id: int
    call_id: str
    name: str
    args: Dict[str, Any] = field(default_factory=dict)
    parallel: bool = False
    started_seq: int = 0
    finished_seq: int = 0
    duration_ms: float = 0.0
    status: str = "pending"
    result_preview: str = ""


@dataclass
class TurnLog:
    """Observability log for a single turn."""

    tool_calls: List[str] = field(default_factory=list)
    iterations: int = 0
    timing_ms: Dict[str, float] = field(default_factory=dict)
    pipeline_total_ms: float = 0.0
    tool_results: Dict[str, Any] = field(default_factory=dict)
    events: List[TurnEvent] = field(default_factory=list)
    tool_executions: List[ToolExecutionLog] = field(default_factory=list)
    _next_seq: int = 0

    def add_event(
        self,
        stage: str,
        message: str,
        **details: Any,
    ) -> TurnEvent:
        """Append an ordered event to the current turn timeline."""
        self._next_seq += 1
        event = TurnEvent(
            seq=self._next_seq,
            stage=stage,
            message=message,
            details=details,
        )
        self.events.append(event)
        return event

    def register_tool_batch(self, tool_calls: List[Dict[str, Any]]) -> int:
        """Register a tool batch and pre-create execution entries."""
        batch_id = len({tool.batch_id for tool in self.tool_executions}) + 1
        parallel = len(tool_calls) > 1
        for tool_call in tool_calls:
            self.tool_executions.append(
                ToolExecutionLog(
                    batch_id=batch_id,
                    call_id=tool_call["id"],
                    name=tool_call["name"],
                    args=tool_call.get("args") or {},
                    parallel=parallel,
                )
            )
        return batch_id

    def mark_tool_started(self, call_id: str) -> ToolExecutionLog | None:
        """Mark a tool execution as started."""
        tool_execution = self._find_tool_execution(call_id)
        if tool_execution is None:
            return None
        tool_execution.status = "running"
        tool_execution.started_seq = self._next_seq + 1
        return tool_execution

    def mark_tool_finished(
        self,
        call_id: str,
        duration_ms: float,
        status: str,
        result_preview: str,
    ) -> ToolExecutionLog | None:
        """Mark a tool execution as finished."""
        tool_execution = self._find_tool_execution(call_id)
        if tool_execution is None:
            return None
        tool_execution.duration_ms = duration_ms
        tool_execution.status = status
        tool_execution.result_preview = result_preview
        tool_execution.finished_seq = self._next_seq + 1
        return tool_execution

    def _find_tool_execution(self, call_id: str) -> ToolExecutionLog | None:
        """Find a tool execution by its call ID."""
        for tool_execution in self.tool_executions:
            if tool_execution.call_id == call_id:
                return tool_execution
        return None

    def format_debug_block(self) -> str:
        """Format a human-readable debug block."""
        lines = ["\n\n---", "**🔍 Debug Info**\n"]
        if self.pipeline_total_ms:
            lines.append(f"**⏱ Total (wall-clock): {self.pipeline_total_ms:.0f}ms**")
        agent_total = sum(ms for key, ms in self.timing_ms.items())
        lines.append(f"**⏱ Agent steps: {agent_total:.0f}ms**")
        for step, ms in self.timing_ms.items():
            lines.append(f"- {step}: {ms:.0f}ms")
        lines.append("\n**📋 Pipeline**")
        lines.append(f"- Iterations: {self.iterations}")
        if self.tool_calls:
            lines.append(f"\n**🔧 Tools: {', '.join(self.tool_calls)}**")
        if self.events:
            lines.append("\n**🪵 Timeline:**")
            for event in self.events:
                lines.append(
                    f"- #{event.seq:02d} [{event.stage}] {event.message}"
                )
        for tool_name, result_data in self.tool_results.items():
            lines.append(f"\n**📦 {tool_name}:**")
            preview = str(result_data)[:300]
            if len(str(result_data)) > 300:
                preview += "…"
            lines.append(f"  {preview}")
        return "\n".join(lines)

    def format_backend_report(self, chat_id: int | str, status: str) -> str:
        """Format a single visually structured backend report for one turn."""
        lines = [
            f"[CHAT TURN REPORT] chat_id={chat_id} status={status}",
            "=" * 72,
            (
                "Summary  | "
                f"iterations={self.iterations}  "
                f"tool_calls={len(self.tool_executions)}  "
                f"batches={len({tool.batch_id for tool in self.tool_executions})}  "
                f"total_ms={self.pipeline_total_ms:.0f}"
            ),
        ]

        if self.tool_executions:
            parallel_batches = sum(
                1 for tool in self.tool_executions if tool.parallel and tool.started_seq
            )
            lines.append(f"Parallel | active_parallel_tools={parallel_batches}")
        else:
            lines.append("Parallel | none")

        lines.append("-" * 72)
        lines.append("Flow")
        for event in self.events:
            detail_parts = [
                f"{key}={self._format_report_value(value)}"
                for key, value in event.details.items()
                if value not in (None, "", [], {})
            ]
            details = f" ({', '.join(detail_parts)})" if detail_parts else ""
            lines.append(
                f"  {event.seq:02d}. {event.stage:<22} {event.message}{details}"
            )

        if self.tool_executions:
            lines.append("-" * 72)
            lines.append("Tools")
            for tool in self.tool_executions:
                mode = "parallel" if tool.parallel else "sequential"
                lines.append(
                    "  "
                    f"batch={tool.batch_id} | {tool.name} | {tool.status} | "
                    f"{mode} | {tool.duration_ms:.0f}ms"
                )
                if tool.args:
                    lines.append(
                        f"    args   : {self._format_report_value(tool.args)}"
                    )
                if tool.result_preview:
                    lines.append(
                        f"    result : {tool.result_preview.replace(chr(10), ' ')}"
                    )

        if self.timing_ms:
            lines.append("-" * 72)
            lines.append("Timings")
            for step, duration in self.timing_ms.items():
                lines.append(f"  {step:<24} {duration:.0f}ms")

        lines.append("=" * 72)
        return "\n".join(lines)

    @staticmethod
    def _format_report_value(value: Any) -> str:
        """Format values for the backend summary report."""
        if isinstance(value, str):
            return value
        if isinstance(value, (list, dict, tuple)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)
