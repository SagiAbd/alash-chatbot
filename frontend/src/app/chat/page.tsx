"use client";

import { KeyboardEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useChat } from "ai/react";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, Send, User } from "lucide-react";
import { Answer } from "@/components/chat/answer";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/use-toast";

interface PublicConfig {
  welcome_title: string;
  welcome_text: string;
  chat_available: boolean;
}

const DEFAULT_CONFIG: PublicConfig = {
  welcome_title: "Алаш мұрасымен сұхбат",
  welcome_text:
    "Алаш қайраткерлері, кітаптар мен ұғымдар туралы сұрақ қойыңыз.",
  chat_available: false,
};

const TOOL_ACTION_KZ: Record<string, string> = {
  search_catalog: "Іздеудемін",
  search_terms: "Пәнсөздерін іздеудемін",
  get_authors_and_books: "Мәліметтер жинаудамын",
  get_book_details: "Мәліметтер жинаудамын",
  get_author_works: "Мәліметтер жинаудамын",
  get_work_content: "Оқудамын",
  search_pages: "Іздеудемін",
  get_page_window: "Оқудамын",
};

function getCurrentStatus(annotations: unknown[] | undefined): string {
  if (!annotations || annotations.length === 0) return "Ойланудамын";
  for (let i = annotations.length - 1; i >= 0; i--) {
    const s = annotations[i] as { step?: string; tool?: string } | null;
    if (s && s.step === "tool_call" && s.tool) {
      return TOOL_ACTION_KZ[s.tool] ?? "Ойланудамын";
    }
  }
  return "Ойланудамын";
}

function AgentStatusText({ annotations }: { annotations: unknown[] | undefined }) {
  const status = getCurrentStatus(annotations);
  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={status}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.25 }}
        className="text-sm text-muted-foreground"
      >
        {status}
        <span className="animate-pulse">...</span>
      </motion.span>
    </AnimatePresence>
  );
}

function getVisibleAssistantContent(content: string): string {
  return content
    .replace(/<think>[\s\S]*?<\/think>/g, "")
    .replace(/<think>[\s\S]*$/, "")
    .trim();
}

export default function PublicChatPage() {
  const { toast } = useToast();
  const [chatId, setChatId] = useState<number | null>(null);
  const [config, setConfig] = useState<PublicConfig>(DEFAULT_CONFIG);
  const [setupError, setSetupError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { messages, input, handleInputChange, handleSubmit, isLoading } = useChat({
    api: chatId ? `/api/public/chat/${chatId}/messages` : "/api/public/chat/unavailable",
    onError: (error: Error) => {
      toast({
        title: "Қате",
        description: error.message || "Жауап алу мүмкін болмады.",
        variant: "destructive",
      });
    },
  });

  useEffect(() => {
    const bootstrap = async () => {
      try {
        const publicConfig = (await api.get("/api/public/config")) as PublicConfig;
        setConfig(publicConfig);
      } catch {
        setConfig(DEFAULT_CONFIG);
      }

      try {
        const data = (await api.post("/api/public/chat")) as { id: number };
        setChatId(data.id);
        setSetupError(null);
      } catch (error) {
        if (error instanceof ApiError) {
          setSetupError(error.message);
        } else {
          setSetupError("Қоғамдық чат қазір қолжетімсіз.");
        }
      }
    };

    void bootstrap();
  }, [toast]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, isLoading]);

  const resizeTextarea = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isLoading && input.trim() && chatId) {
        handleSubmit(e as never);
        if (textareaRef.current) {
          textareaRef.current.style.height = "auto";
        }
      }
    }
  };

  const lastMessage = messages[messages.length - 1];

  return (
    <main className="min-h-screen bg-gray-50 text-black">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-8">
          <Link href="/" className="inline-flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-600 text-sm font-semibold text-white shadow-sm">
              A
            </span>
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-600">
                Alash Chatbot
              </p>
              <p className="mt-1 text-sm text-gray-500">
                Қоғамдық чат
              </p>
            </div>
          </Link>
          <Link
            href="/admin/login"
            className="px-5 py-2.5 bg-gray-200 text-gray-800 rounded-full text-sm font-medium transition-all duration-300 hover:bg-gray-300"
          >
            Әкімші кіруі
          </Link>
        </div>

        <div className="bg-white rounded-3xl shadow-sm border overflow-hidden">
          <div className="border-b px-6 py-5">
            <h1 className="text-2xl font-bold text-gray-900">
              {config.welcome_title}
            </h1>
            <p className="mt-2 text-sm text-gray-600">{config.welcome_text}</p>
          </div>

          <div ref={scrollRef} className="h-[60vh] overflow-y-auto px-6 py-6 space-y-6">
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center mb-4 opacity-50">
                  <Bot className="h-8 w-8 text-muted-foreground" />
                </div>
                <p className="text-lg font-medium">Сұрағыңызды жазыңыз</p>
                <p className="text-sm mt-1 text-center">
                  Бет жаңартылса, қоғамдық чат жаңа сессиядан басталады.
                </p>
              </div>
            )}

            {messages.map((message) => {
              if (message.role === "user") {
                return (
                  <div key={message.id} className="flex justify-end">
                    <div className="max-w-[90%] rounded-2xl bg-primary text-primary-foreground px-4 py-3 shadow-sm whitespace-pre-wrap">
                      <div className="mb-2 flex items-center gap-2 text-xs text-primary-foreground/80">
                        <User className="h-3.5 w-3.5" />
                        Сіз
                      </div>
                      {message.content}
                    </div>
                  </div>
                );
              }

              return (
                <div key={message.id} className="flex items-start gap-3">
                  <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center shrink-0 mt-1 shadow-sm">
                    <Bot className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div className="max-w-[90%] rounded-2xl border bg-card px-4 py-3 shadow-sm">
                    <Answer
                      markdown={getVisibleAssistantContent(message.content)}
                      isStreaming={isLoading && message.id === lastMessage?.id}
                    />
                  </div>
                </div>
              );
            })}

            {isLoading && (
              <div className="flex items-start gap-3">
                <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center shrink-0 mt-1 shadow-sm">
                  <Bot className="h-4 w-4 text-muted-foreground" />
                </div>
                <div className="rounded-2xl border bg-card px-4 py-3 shadow-sm">
                  <AgentStatusText
                    annotations={
                      lastMessage?.role === "assistant"
                        ? (lastMessage as { annotations?: unknown[] }).annotations
                        : undefined
                    }
                  />
                </div>
              </div>
            )}
          </div>

          <div className="border-t px-6 py-5">
            {setupError && (
              <div className="mb-4 rounded-md bg-amber-50 px-4 py-3 text-sm text-amber-700">
                {setupError}
              </div>
            )}

            <form onSubmit={handleSubmit} className="flex items-end gap-3">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => {
                  handleInputChange(e);
                  resizeTextarea();
                }}
                onKeyDown={onKeyDown}
                placeholder={
                  chatId
                    ? "Сұрағыңызды осында жазыңыз..."
                    : "Қоғамдық чат дайындалып жатыр..."
                }
                disabled={!chatId || isLoading}
                rows={1}
                className="min-h-[52px] flex-1 resize-none rounded-2xl border border-gray-300 bg-white px-4 py-3 text-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              />
              <button
                type="submit"
                disabled={!chatId || isLoading || !input.trim()}
                className="h-12 w-12 rounded-full bg-blue-600 text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
              >
                <Send className="mx-auto h-4 w-4" />
              </button>
            </form>
          </div>
        </div>
      </div>
    </main>
  );
}
