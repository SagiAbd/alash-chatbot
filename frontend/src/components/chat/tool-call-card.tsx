"use client";

import { FC } from "react";
import { motion } from "framer-motion";
import { Loader2, CheckCircle2, Search, BookOpen, Users, FileText } from "lucide-react";

type ToolState = "calling" | "done";

interface ToolCallCardProps {
  toolName: string;
  args?: string;
  state: ToolState;
  summary?: string;
}

const TOOL_CONFIG: Record<
  string,
  { label: string; icon: typeof Search }
> = {
  get_authors_and_books: { label: "Авторлар мен кітаптар", icon: Users },
  get_book_details:      { label: "Кітап мәліметтері",     icon: BookOpen },
  get_author_works:      { label: "Автор шығармалары",     icon: Users },
  get_work_content:      { label: "Шығарма мәтіні",        icon: FileText },
  search_catalog:        { label: "Каталогта іздеу",       icon: Search },
  read_pages:            { label: "Беттерді оқу",          icon: Search },
  search_terms:          { label: "Пәнсөздерін іздеу",     icon: BookOpen },
};

function formatArgs(args: string): string {
  if (!args || args === "{}") return "";
  try {
    const parsed = JSON.parse(args);
    return Object.entries(parsed)
      .map(([k, v]) => `${k}: ${v}`)
      .join(", ");
  } catch {
    return args;
  }
}

export const ToolCallCard: FC<ToolCallCardProps> = ({
  toolName,
  args,
  state,
  summary,
}) => {
  const config = TOOL_CONFIG[toolName] || {
    label: toolName,
    icon: Search,
  };
  const Icon = config.icon;
  const argsFormatted = args ? formatArgs(args) : "";

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.15 }}
      className={`rounded-lg border px-3 py-2 text-xs transition-colors ${
        state === "done"
          ? "border-l-4 border-l-emerald-500 border-y-border/50 border-r-border/50 bg-emerald-50/50 dark:bg-emerald-950/10"
          : "border-l-4 border-l-blue-400 border-y-border/50 border-r-border/50 bg-blue-50/50 dark:bg-blue-950/10"
      }`}
    >
      <div className="flex items-center gap-2">
        {state === "calling" ? (
          <Loader2 className="h-3.5 w-3.5 text-blue-500 animate-spin flex-shrink-0" />
        ) : (
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 flex-shrink-0" />
        )}

        <Icon className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />

        <span
          className={`font-medium ${
            state === "done"
              ? "text-emerald-700 dark:text-emerald-400"
              : "text-blue-700 dark:text-blue-400"
          }`}
        >
          {config.label}
        </span>

        {argsFormatted && (
          <span className="text-muted-foreground truncate">
            ({argsFormatted})
          </span>
        )}
      </div>

      {state === "done" && summary && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          transition={{ duration: 0.15 }}
          className="mt-1.5 pl-[22px] text-muted-foreground truncate"
        >
          {summary}
        </motion.div>
      )}
    </motion.div>
  );
};
