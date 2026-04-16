"use client";

import { useEffect, useRef, useState, useMemo, useCallback, KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import { useChat } from "ai/react";
import { Send, User, Bot } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import DashboardLayout from "@/components/layout/dashboard-layout";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/use-toast";
import { Answer } from "@/components/chat/answer";

const TOOL_ACTION_KZ: Record<string, string> = {
  search_catalog:        "Іздеудемін",
  search_terms:          "Пәнсөздерін іздеудемін",
  get_authors_and_books: "Мәліметтер жинаудамын",
  get_book_details:      "Мәліметтер жинаудамын",
  get_author_works:      "Мәліметтер жинаудамын",
  get_work_content:      "Оқудамын",
  search_pages:          "Іздеудемін",
};

// Backend streams step events as 8:[{...}] — AI SDK v4 maps code 8 to
// "message_annotations", so these end up on `lastMessage.annotations`
// (NOT on useChat's top-level `data`). Read from there.
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

function useSmoothedStatus(annotations: unknown[] | undefined, minMs = 1500): string {
  const [displayed, setDisplayed] = useState("Ойланудамын");
  const pendingRef = useRef<string | null>(null);
  const lastChangeRef = useRef<number>(Date.now());

  const currentStatus = getCurrentStatus(annotations);

  useEffect(() => {
    const elapsed = Date.now() - lastChangeRef.current;
    if (elapsed >= minMs) {
      setDisplayed(currentStatus);
      lastChangeRef.current = Date.now();
      pendingRef.current = null;
    } else {
      pendingRef.current = currentStatus;
      const timer = setTimeout(() => {
        if (pendingRef.current) {
          setDisplayed(pendingRef.current);
          lastChangeRef.current = Date.now();
          pendingRef.current = null;
        }
      }, minMs - elapsed);
      return () => clearTimeout(timer);
    }
  }, [currentStatus, minMs]);

  return displayed;
}

function AgentStatusText({ annotations }: { annotations: unknown[] | undefined }) {
  const status = useSmoothedStatus(annotations);
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

interface ChatMessage {
  id: number;
  content: string;
  role: "assistant" | "user";
  created_at: string;
}

interface Chat {
  id: number;
  title: string;
  messages: ChatMessage[];
}

function getVisibleAssistantContent(content: string): string {
  return content
    .replace(/<think>[\s\S]*?<\/think>/g, "")
    .replace(/<think>[\s\S]*$/, "")
    .trim();
}

export default function ChatPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const prevScrollTopRef = useRef(0);
  const lastUserMsgRef = useRef<HTMLDivElement>(null);
  const justSubmittedRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { toast } = useToast();
  const [isInitialLoad, setIsInitialLoad] = useState(true);

  const {
    messages,
    input,
    handleInputChange,
    handleSubmit: chatHandleSubmit,
    isLoading,
    setMessages,
  } = useChat({
    api: `/api/chat/${params.id}/messages`,
    headers: {
      Authorization: `Bearer ${
        typeof window !== "undefined"
          ? window.localStorage.getItem("token")
          : ""
      }`,
    },
    onError: (error: Error) => {
      toast({
        title: "Error",
        description: error.message || "Failed to get a response. Please try again.",
        variant: "destructive",
      });
    },
  });

  useEffect(() => {
    if (isInitialLoad) {
      fetchChat();
      setIsInitialLoad(false);
    }
  }, [isInitialLoad]);

  // ── Smart scroll system ──────────────────────────────────────

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const scrollTop = el.scrollTop;
    const prev = prevScrollTopRef.current;
    prevScrollTopRef.current = scrollTop;
    if (scrollTop < prev) {
      shouldAutoScrollRef.current = false;
      return;
    }
    if (el.scrollHeight - scrollTop - el.clientHeight < 80) {
      shouldAutoScrollRef.current = true;
    }
  }, []);

  // Scroll user message to top on submit
  useEffect(() => {
    if (isInitialLoad) return;
    if (
      justSubmittedRef.current &&
      messages.length > 0 &&
      messages[messages.length - 1].role === "user"
    ) {
      justSubmittedRef.current = false;
      shouldAutoScrollRef.current = true;
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          const container = scrollContainerRef.current;
          const userMsg = lastUserMsgRef.current;
          if (container && userMsg) {
            const containerTop = container.getBoundingClientRect().top;
            const userTop = userMsg.getBoundingClientRect().top;
            const targetTop =
              container.scrollTop + (userTop - containerTop) - 24;
            container.scrollTo({
              top: Math.max(0, targetTop),
              behavior: "auto",
            });
          }
        });
      });
    }
  }, [messages, isInitialLoad]);

  // Smooth auto-scroll during streaming via rAF — no jitter
  useEffect(() => {
    if (!isLoading) return;
    const container = scrollContainerRef.current;
    if (!container) return;
    let raf: number;
    const tick = () => {
      if (shouldAutoScrollRef.current) {
        const maxScrollTop = container.scrollHeight - container.clientHeight;
        if (Math.abs(maxScrollTop - container.scrollTop) > 1) {
          container.scrollTop = maxScrollTop;
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [isLoading]);

  const fetchChat = async () => {
    try {
      const data: Chat = await api.get(`/api/chat/${params.id}`);
      const formattedMessages = data.messages
        .filter((msg) => !(msg.role === "assistant" && !msg.content.trim()))
        .map((msg) => {
          let content = msg.content || "";
          if (msg.role === "assistant" && content.includes("__LLM_RESPONSE__")) {
            content = content.split("__LLM_RESPONSE__").pop() || "";
          }
          return {
            id: msg.id.toString(),
            role: msg.role,
            content,
          };
        });
      setMessages(formattedMessages);
    } catch (error) {
      console.error("Failed to fetch chat:", error);
      if (error instanceof ApiError) {
        toast({
          title: "Error",
          description: error.message,
          variant: "destructive",
        });
      }
      router.push("/admin/chat");
    }
  };

  const resizeTextarea = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isLoading && input.trim()) {
        justSubmittedRef.current = true;
        shouldAutoScrollRef.current = true;
        chatHandleSubmit(e as any);
        if (textareaRef.current) {
          textareaRef.current.style.height = "auto";
        }
      }
    }
  };

  // Find last user message index for ref assignment
  const lastUserMsgIdx = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") return i;
    }
    return -1;
  }, [messages]);

  const lastMessage = messages[messages.length - 1];
  const lastVisibleAssistantContent =
    lastMessage?.role === "assistant"
      ? getVisibleAssistantContent(lastMessage.content)
      : "";
  const showLoadingDots =
    isLoading &&
    (!lastMessage ||
      lastMessage.role !== "assistant" ||
      lastVisibleAssistantContent.length === 0);

  return (
    <DashboardLayout>
      <div className="flex flex-col h-[calc(100vh-5rem)] relative">
        {/* Messages area */}
        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto px-4 py-6 space-y-6 pb-[200px]"
        >
          {/* Empty state */}
          {messages.length === 0 && !isLoading && (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
              <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center mb-4 opacity-50">
                <Bot className="h-8 w-8 text-muted-foreground" />
              </div>
              <p className="text-lg font-medium">
                Қош келдіңіз!
              </p>
              <p className="text-sm mt-1">Сұрағыңызды жазыңыз</p>
            </div>
          )}

          {/* Messages */}
          {messages.map((message, index) => {
            if (message.role === "user") {
              return (
                <div
                  key={message.id}
                  ref={index === lastUserMsgIdx ? lastUserMsgRef : undefined}
                  className="flex items-start justify-end gap-3 chat-message-in"
                >
                  <div className="max-w-[95%] lg:max-w-[85%] rounded-2xl bg-primary text-primary-foreground px-4 py-3 shadow-sm whitespace-pre-wrap">
                    {message.content}
                  </div>
                  <div className="h-8 w-8 rounded-full bg-primary/90 flex items-center justify-center shrink-0 mt-1 shadow-sm">
                    <User className="h-4 w-4 text-primary-foreground" />
                  </div>
                </div>
              );
            }

            if (message.role === "assistant") {
              const isMsgStreaming =
                isLoading && index === messages.length - 1;
              const visibleContent = getVisibleAssistantContent(message.content);

              if (!visibleContent) {
                return null;
              }

              return (
                <div
                  key={message.id}
                  className="flex items-start gap-3 chat-message-in"
                >
                  <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center shrink-0 mt-1 shadow-sm">
                    <Bot className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div className="max-w-[95%] lg:max-w-[85%] rounded-2xl bg-muted/60 px-4 py-3 shadow-sm">
                    <Answer
                      markdown={visibleContent}
                      isStreaming={isMsgStreaming}
                    />
                  </div>
                </div>
              );
            }

            return null;
          })}

          {/* Loading status */}
          {showLoadingDots && (
            <div className="flex items-start gap-3 chat-message-in">
              <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center shrink-0 mt-1 shadow-sm">
                <Bot className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="rounded-2xl bg-muted/60 px-5 py-4 shadow-sm">
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

          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="absolute bottom-0 left-0 right-0 border-t bg-background/95 backdrop-blur-sm p-3 sm:p-4">
          <form
            onSubmit={(e) => {
              justSubmittedRef.current = true;
              shouldAutoScrollRef.current = true;
              chatHandleSubmit(e);
              if (textareaRef.current) textareaRef.current.style.height = "auto";
            }}
            className="mx-auto flex items-end gap-3 max-w-4xl"
          >
            <div className="flex-1 min-w-0 rounded-xl border border-input bg-background shadow-sm focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-1 transition-shadow">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => {
                  handleInputChange(e);
                  resizeTextarea();
                }}
                onKeyDown={handleKeyDown}
                placeholder="Сұрағыңызды жазыңыз..."
                rows={1}
                className="min-h-[44px] w-full resize-none bg-transparent px-4 py-[11px] text-sm leading-6 placeholder:text-muted-foreground focus:outline-none"
                style={{ maxHeight: 160 }}
              />
            </div>
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="inline-flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm transition-all hover:scale-105 hover:bg-primary/90 active:scale-95 disabled:pointer-events-none disabled:opacity-40 disabled:hover:scale-100"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>
      </div>
    </DashboardLayout>
  );
}
