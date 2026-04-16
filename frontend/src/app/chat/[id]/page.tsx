"use client";

import {
  KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { useChat } from "ai/react";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, Send, User } from "lucide-react";
import DashboardLayout from "@/components/layout/dashboard-layout";
import { Answer } from "@/components/chat/answer";
import { ApiError, api } from "@/lib/api";
import { buildChatHeaders } from "@/lib/chat-headers";
import { useToast } from "@/components/ui/use-toast";

const TOOL_ACTION_KZ: Record<string, string> = {
  search_catalog: "Іздеудемін",
  search_terms: "Пәнсөздерін іздеудемін",
  get_authors_and_books: "Мәліметтер жинаудамын",
  get_book_details: "Мәліметтер жинаудамын",
  get_author_works: "Мәліметтер жинаудамын",
  get_work_content: "Оқудамын",
  search_pages: "Іздеудемін",
};

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

function getCurrentStatus(annotations: unknown[] | undefined): string {
  if (!annotations || annotations.length === 0) {
    return "Ойланудамын";
  }
  for (let i = annotations.length - 1; i >= 0; i -= 1) {
    const step = annotations[i] as { step?: string; tool?: string } | null;
    if (step?.step === "tool_call" && step.tool) {
      return TOOL_ACTION_KZ[step.tool] ?? "Ойланудамын";
    }
  }
  return "Ойланудамын";
}

function useSmoothedStatus(
  annotations: unknown[] | undefined,
  minMs = 1500,
): string {
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
      return;
    }

    pendingRef.current = currentStatus;
    const timer = setTimeout(() => {
      if (pendingRef.current) {
        setDisplayed(pendingRef.current);
        lastChangeRef.current = Date.now();
        pendingRef.current = null;
      }
    }, minMs - elapsed);
    return () => clearTimeout(timer);
  }, [currentStatus, minMs]);

  return displayed;
}

function AgentStatusText({
  annotations,
}: {
  annotations: unknown[] | undefined;
}) {
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

function getVisibleAssistantContent(content: string): string {
  return content
    .replace(/<think>[\s\S]*?<\/think>/g, "")
    .replace(/<think>[\s\S]*$/, "")
    .trim();
}

export default function ChatPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const { toast } = useToast();
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const prevScrollTopRef = useRef(0);
  const shouldAutoScrollRef = useRef(true);
  const lastUserMsgRef = useRef<HTMLDivElement>(null);
  const justSubmittedRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
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
    headers: buildChatHeaders(),
    onError: (error: Error) => {
      toast({
        title: "Қате",
        description: error.message || "Жауап алу сәтсіз аяқталды. Қайта байқап көріңіз.",
        variant: "destructive",
      });
    },
  });

  useEffect(() => {
    if (!isInitialLoad) {
      return;
    }

    const fetchChat = async () => {
      try {
        const data = (await api.get(`/api/chat/${params.id}`)) as Chat;
        const formattedMessages = data.messages
          .filter((msg) => !(msg.role === "assistant" && !msg.content.trim()))
          .map((msg) => {
            let content = msg.content || "";
            if (
              msg.role === "assistant" &&
              content.includes("__LLM_RESPONSE__")
            ) {
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
        if (error instanceof ApiError) {
          toast({
            title: "Қате",
            description: error.message,
            variant: "destructive",
          });
        }
        router.push("/");
      } finally {
        setIsInitialLoad(false);
      }
    };

    void fetchChat();
  }, [isInitialLoad, params.id, router, setMessages, toast]);

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) {
      return;
    }

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

  useEffect(() => {
    if (
      isInitialLoad ||
      !justSubmittedRef.current ||
      messages.length === 0 ||
      messages[messages.length - 1].role !== "user"
    ) {
      return;
    }

    justSubmittedRef.current = false;
    shouldAutoScrollRef.current = true;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const container = scrollContainerRef.current;
        const userMsg = lastUserMsgRef.current;
        if (!container || !userMsg) {
          return;
        }

        const containerTop = container.getBoundingClientRect().top;
        const userTop = userMsg.getBoundingClientRect().top;
        const targetTop = container.scrollTop + (userTop - containerTop) - 24;
        container.scrollTo({
          top: Math.max(0, targetTop),
          behavior: "auto",
        });
      });
    });
  }, [isInitialLoad, messages]);

  useEffect(() => {
    if (!isLoading) {
      return;
    }

    const container = scrollContainerRef.current;
    if (!container) {
      return;
    }

    let raf = 0;
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

  const resizeTextarea = () => {
    const el = textareaRef.current;
    if (!el) {
      return;
    }
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!isLoading && input.trim()) {
        justSubmittedRef.current = true;
        shouldAutoScrollRef.current = true;
        chatHandleSubmit(event as never);
        if (textareaRef.current) {
          textareaRef.current.style.height = "auto";
        }
      }
    }
  };

  const lastUserMsgIdx = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === "user") {
        return i;
      }
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
      <div className="relative flex h-[calc(100vh-5rem)] flex-col">
        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="flex-1 space-y-6 overflow-y-auto px-4 py-6 pb-[200px]"
        >
          {messages.length === 0 && !isLoading && (
            <div className="flex h-full flex-col items-center justify-center text-muted-foreground">
              <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-muted opacity-50">
                <Bot className="h-8 w-8 text-muted-foreground" />
              </div>
              <p className="text-lg font-medium">
                Қош келдіңіз!
              </p>
              <p className="mt-1 text-sm">Сұрағыңызды жазыңыз</p>
            </div>
          )}

          {messages.map((message, index) => {
            if (message.role === "user") {
              return (
                <div
                  key={message.id}
                  ref={index === lastUserMsgIdx ? lastUserMsgRef : undefined}
                  className="chat-message-in flex items-start justify-end gap-3"
                >
                  <div className="max-w-[95%] whitespace-pre-wrap rounded-2xl bg-primary px-4 py-3 text-primary-foreground shadow-sm lg:max-w-[85%]">
                    {message.content}
                  </div>
                  <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/90 shadow-sm">
                    <User className="h-4 w-4 text-primary-foreground" />
                  </div>
                </div>
              );
            }

            const isStreaming = isLoading && index === messages.length - 1;
            const visibleContent = getVisibleAssistantContent(message.content);
            if (!visibleContent) {
              return null;
            }

            return (
              <div key={message.id} className="chat-message-in flex items-start gap-3">
                <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted shadow-sm">
                  <Bot className="h-4 w-4 text-muted-foreground" />
                </div>
                <div className="max-w-[95%] rounded-2xl bg-muted/60 px-4 py-3 shadow-sm lg:max-w-[85%]">
                  <Answer markdown={visibleContent} isStreaming={isStreaming} />
                </div>
              </div>
            );
          })}

          {showLoadingDots && (
            <div className="chat-message-in flex items-start gap-3">
              <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted shadow-sm">
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
        </div>

        <div className="absolute bottom-0 left-0 right-0 border-t bg-background/95 p-3 backdrop-blur-sm sm:p-4">
          <form
            onSubmit={(event) => {
              justSubmittedRef.current = true;
              shouldAutoScrollRef.current = true;
              chatHandleSubmit(event);
              if (textareaRef.current) {
                textareaRef.current.style.height = "auto";
              }
            }}
            className="mx-auto flex max-w-4xl items-end gap-3"
          >
            <div className="min-w-0 flex-1 rounded-xl border border-input bg-background shadow-sm transition-shadow focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-1">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(event) => {
                  handleInputChange(event);
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
