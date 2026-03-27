"use client";

import { FC, useEffect, useRef } from "react";
import { AnimatePresence } from "framer-motion";
import { ThinkingBubble } from "./thinking-bubble";
import { ToolCallCard } from "./tool-call-card";

export interface AgentStep {
  type: "step";
  step: "thinking" | "tool_call" | "tool_result";
  content?: string;
  tool?: string;
  args?: string;
  summary?: string;
}

/**
 * Merge raw step events into visual blocks:
 * - thinking steps → ThinkingBubble
 * - tool_call + tool_result pairs → ToolCallCard (with state)
 * - tool_call without result yet → ToolCallCard (calling state)
 */
interface VisualBlock {
  kind: "thinking" | "tool";
  // thinking
  content?: string;
  isThinkingStreaming?: boolean;
  // tool
  toolName?: string;
  args?: string;
  toolState?: "calling" | "done";
  summary?: string;
}

function buildVisualBlocks(
  steps: AgentStep[],
  isStreaming: boolean
): VisualBlock[] {
  const blocks: VisualBlock[] = [];
  const toolResults = new Map<string, string>();

  // First pass: collect tool results by tool name
  for (const step of steps) {
    if (step.step === "tool_result" && step.tool) {
      toolResults.set(step.tool, step.summary || "");
    }
  }

  // Second pass: build blocks
  const seenTools = new Set<string>();
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];

    if (step.step === "thinking") {
      blocks.push({
        kind: "thinking",
        content: step.content || "",
        isThinkingStreaming: isStreaming && i === steps.length - 1,
      });
    } else if (step.step === "tool_call" && step.tool) {
      // Avoid duplicates for same tool in same turn
      const key = `${step.tool}:${step.args || ""}`;
      if (seenTools.has(key)) continue;
      seenTools.add(key);

      const result = toolResults.get(step.tool);
      blocks.push({
        kind: "tool",
        toolName: step.tool,
        args: step.args,
        toolState: result !== undefined ? "done" : "calling",
        summary: result,
      });
    }
    // tool_result handled via merge above
  }

  return blocks;
}

export const AgentSteps: FC<{
  steps: AgentStep[];
  isStreaming: boolean;
}> = ({ steps, isStreaming }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollIntoView({
        behavior: "smooth",
        block: "end",
      });
    }
  }, [steps.length]);

  if (steps.length === 0) return null;

  const blocks = buildVisualBlocks(steps, !isStreaming);

  return (
    <div ref={containerRef} className="flex flex-col gap-2">
      <AnimatePresence mode="popLayout">
        {blocks.map((block, i) => {
          if (block.kind === "thinking") {
            return (
              <ThinkingBubble
                key={`think-${i}`}
                content={block.content || ""}
                isStreaming={block.isThinkingStreaming || false}
              />
            );
          }
          return (
            <ToolCallCard
              key={`tool-${block.toolName}-${i}`}
              toolName={block.toolName || ""}
              args={block.args}
              state={block.toolState || "calling"}
              summary={block.summary}
            />
          );
        })}
      </AnimatePresence>
    </div>
  );
};
