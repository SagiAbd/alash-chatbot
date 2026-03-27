"use client";

import { FC, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Brain, ChevronDown } from "lucide-react";

interface ThinkingBubbleProps {
  content: string;
  isStreaming: boolean;
  durationMs?: number;
}

export const ThinkingBubble: FC<ThinkingBubbleProps> = ({
  content,
  isStreaming,
  durationMs,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const tokenCount = content.length;
  const tokenLabel =
    tokenCount > 1000
      ? `${(tokenCount / 1000).toFixed(1)}k chars`
      : `${tokenCount} chars`;

  const durationLabel = durationMs
    ? `${(durationMs / 1000).toFixed(1)}s`
    : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="rounded-xl border-l-4 border-violet-400 bg-violet-50 dark:bg-violet-950/20 overflow-hidden"
    >
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs text-violet-700 dark:text-violet-300 hover:bg-violet-100/50 dark:hover:bg-violet-900/30 transition-colors"
      >
        <Brain className="h-3.5 w-3.5 flex-shrink-0" />
        <span className="font-medium">
          {isStreaming ? "Thinking..." : "Thought"}
        </span>
        {!isStreaming && durationLabel && (
          <span className="text-violet-500/70">for {durationLabel}</span>
        )}
        <span className="ml-auto text-violet-400 text-[10px]">
          {tokenLabel}
        </span>
        <motion.div
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <ChevronDown className="h-3.5 w-3.5 text-violet-400" />
        </motion.div>
      </button>

      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 text-xs text-violet-700/80 dark:text-violet-300/80 whitespace-pre-wrap leading-relaxed border-t border-violet-200/50 dark:border-violet-800/50 pt-2">
              {content}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {isStreaming && (
        <div className="px-3 pb-2">
          <div className="flex gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse" />
            <div className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse [animation-delay:0.3s]" />
            <div className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-pulse [animation-delay:0.6s]" />
          </div>
        </div>
      )}
    </motion.div>
  );
};
