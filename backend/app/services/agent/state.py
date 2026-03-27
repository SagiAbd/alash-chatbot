"""Agent state for the LangGraph-based Alash chatbot."""

from typing import Optional, List, Dict, Any, TypedDict, Annotated
from dataclasses import dataclass, field
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """LangGraph state for the Alash RAG agent."""
    messages: Annotated[List[BaseMessage], add_messages]
    question: str
    turn_log: "TurnLog"


@dataclass
class TurnLog:
    """Observability log for a single turn."""
    tool_calls: List[str] = field(default_factory=list)
    iterations: int = 0
    timing_ms: Dict[str, float] = field(default_factory=dict)
    pipeline_total_ms: float = 0.0
    tool_results: Dict[str, Any] = field(default_factory=dict)

    def format_debug_block(self) -> str:
        """Format a human-readable debug block."""
        lines = ["\n\n---", "**🔍 Debug Info**\n"]
        if self.pipeline_total_ms:
            lines.append(f"**⏱ Total (wall-clock): {self.pipeline_total_ms:.0f}ms**")
        agent_total = sum(ms for key, ms in self.timing_ms.items())
        lines.append(f"**⏱ Agent steps: {agent_total:.0f}ms**")
        for step, ms in self.timing_ms.items():
            lines.append(f"- {step}: {ms:.0f}ms")
        lines.append(f"\n**📋 Pipeline**")
        lines.append(f"- Iterations: {self.iterations}")
        if self.tool_calls:
            lines.append(f"\n**🔧 Tools: {', '.join(self.tool_calls)}**")
        for tool_name, result_data in self.tool_results.items():
            lines.append(f"\n**📦 {tool_name}:**")
            preview = str(result_data)[:300]
            if len(str(result_data)) > 300:
                preview += "…"
            lines.append(f"  {preview}")
        return "\n".join(lines)
