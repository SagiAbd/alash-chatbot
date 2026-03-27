"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useChat } from "ai/react";
import { Send, User } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import DashboardLayout from "@/components/layout/dashboard-layout";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/use-toast";
import { Answer } from "@/components/chat/answer";
import { AgentSteps, AgentStep } from "@/components/chat/agent-steps";
import { ThinkingBubble } from "@/components/chat/thinking-bubble";

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

function parseAssistantMessage(content: string, isStreaming: boolean) {
  const blocks: { type: "think" | "text"; content: string; isStreaming?: boolean }[] = [];
  let i = 0;
  while (i < content.length) {
    const thinkStart = content.indexOf("<think>", i);
    if (thinkStart === -1) {
      const rest = content.substring(i);
      if (rest.trim()) blocks.push({ type: "text", content: rest });
      break;
    }
    
    if (thinkStart > i) {
      const textBefore = content.substring(i, thinkStart);
      if (textBefore.trim()) blocks.push({ type: "text", content: textBefore });
    }
    
    const thinkEndToken = "</think>";
    const thinkEnd = content.indexOf(thinkEndToken, thinkStart);
    
    if (thinkEnd === -1) {
      const thinkContent = content.substring(thinkStart + "<think>".length);
      blocks.push({ type: "think", content: thinkContent, isStreaming });
      break;
    } else {
      const thinkContent = content.substring(thinkStart + "<think>".length, thinkEnd);
      blocks.push({ type: "think", content: thinkContent, isStreaming: false });
      i = thinkEnd + thinkEndToken.length;
    }
  }
  return blocks;
}

export default function ChatPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { toast } = useToast();
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([]);
  const [isStreamingAnswer, setIsStreamingAnswer] = useState(false);

  const {
    messages,
    data,
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
    onFinish: () => {
      setIsStreamingAnswer(false);
    },
  });

  // Parse step events from data stream annotations
  useEffect(() => {
    if (!data || data.length === 0) return;

    const steps: AgentStep[] = [];
    for (const item of data) {
      if (
        item &&
        typeof item === "object" &&
        "type" in item &&
        (item as any).type === "step"
      ) {
        steps.push(item as unknown as AgentStep);
      }
    }
    if (steps.length > 0) {
      setAgentSteps(steps);
    }
  }, [data]);

  // Detect when answer tokens start streaming
  useEffect(() => {
    if (!isLoading) {
      setIsStreamingAnswer(false);
      return;
    }
    const lastMsg = messages[messages.length - 1];
    if (lastMsg?.role === "assistant" && lastMsg.content.length > 0) {
      setIsStreamingAnswer(true);
    }
  }, [messages, isLoading]);

  useEffect(() => {
    if (isInitialLoad) {
      fetchChat();
      setIsInitialLoad(false);
    }
  }, [isInitialLoad]);

  useEffect(() => {
    if (!isInitialLoad) {
      scrollToBottom();
    }
  }, [messages, isInitialLoad, agentSteps]);

  const fetchChat = async () => {
    try {
      const data: Chat = await api.get(`/api/chat/${params.id}`);
      const formattedMessages = data.messages.map((msg) => {
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
      router.push("/dashboard/chat");
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      setIsStreamingAnswer(false);
      chatHandleSubmit(e);
    },
    [chatHandleSubmit]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (input.trim() && !isLoading) {
          handleSubmit(e as unknown as React.FormEvent);
        }
      }
    },
    [input, isLoading, handleSubmit]
  );

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [input]);

  // Check if we should show agent steps block (separate from answer)
  const showAgentSteps = isLoading && agentSteps.length > 0;
  const showLoadingDots =
    isLoading &&
    agentSteps.length === 0 &&
    messages[messages.length - 1]?.role !== "assistant";

  return (
    <DashboardLayout>
      <div className="flex flex-col h-[calc(100vh-5rem)] relative">
        {/* Messages area */}
        <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6 pb-[140px]">
          {/* Empty state */}
          {messages.length === 0 && !isLoading && (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
              <img
                src="/logo.png"
                className="h-16 w-16 rounded-full mb-4 opacity-50"
                alt="logo"
              />
              <p className="text-lg font-medium">
                Алаш чатботына қош келдіңіз
              </p>
              <p className="text-sm mt-1">Сұрағыңызды жазыңыз</p>
            </div>
          )}

          {/* Messages */}
          <AnimatePresence mode="popLayout">
            {messages.map((message) => {
              if (message.role === "user") {
                return (
                  <motion.div
                    key={message.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2 }}
                    className="flex justify-end items-start gap-3"
                  >
                    <div className="max-w-[85%] min-w-0">
                      <div className="rounded-2xl rounded-tr-sm bg-primary text-primary-foreground px-4 py-3 shadow-sm">
                        <div className="prose prose-sm prose-invert max-w-full">
                          <p className="whitespace-pre-wrap m-0">
                            {message.content}
                          </p>
                        </div>
                      </div>
                    </div>
                    <div className="w-8 h-8 flex-shrink-0 rounded-full bg-primary flex items-center justify-center">
                      <User className="h-4 w-4 text-primary-foreground" />
                    </div>
                  </motion.div>
                );
              }

              if (message.role === "assistant") {
                const isMsgStreaming =
                  isLoading &&
                  message.id === messages[messages.length - 1]?.id &&
                  isStreamingAnswer;
                const blocks = parseAssistantMessage(message.content, isMsgStreaming);

                return (
                  <motion.div
                    key={message.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2 }}
                    className="flex justify-start items-start gap-3"
                  >
                    <div className="w-8 h-8 flex-shrink-0 flex items-center justify-center">
                      <img
                        src="/logo.png"
                        className="h-8 w-8 rounded-full"
                        alt="logo"
                      />
                    </div>
                    <div className="max-w-[85%] min-w-0 flex flex-col gap-2">
                      {blocks.length === 0 ? (
                        <div className="rounded-2xl rounded-tl-sm bg-muted/50 px-4 py-3 shadow-sm">
                          <Answer markdown="" />
                        </div>
                      ) : (
                        blocks.map((block, idx) => {
                          if (block.type === "think") {
                            return (
                              <ThinkingBubble
                                key={idx}
                                content={block.content}
                                isStreaming={block.isStreaming || false}
                              />
                            );
                          }
                          return (
                            <div
                              key={idx}
                              className="rounded-2xl rounded-tl-sm bg-muted/50 px-4 py-3 shadow-sm"
                            >
                              <Answer markdown={block.content} />
                            </div>
                          );
                        })
                      )}
                    </div>
                  </motion.div>
                );
              }

              return null;
            })}
          </AnimatePresence>

          {/* Agent reasoning & tool calls — separate block below messages */}
          {showAgentSteps && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className="flex justify-start items-start gap-3"
            >
              <div className="w-8 h-8 flex-shrink-0 flex items-center justify-center">
                <img
                  src="/logo.png"
                  className="h-8 w-8 rounded-full"
                  alt="logo"
                />
              </div>
              <div className="max-w-[85%] min-w-0">
                <AgentSteps
                  steps={agentSteps}
                  isStreaming={isStreamingAnswer}
                />
              </div>
            </motion.div>
          )}

          {/* Loading dots when no steps yet */}
          {showLoadingDots && (
            <div className="flex justify-start items-start gap-3">
              <div className="w-8 h-8 flex-shrink-0 flex items-center justify-center">
                <img
                  src="/logo.png"
                  className="h-8 w-8 rounded-full opacity-50"
                  alt="logo"
                />
              </div>
              <div className="rounded-2xl rounded-tl-sm bg-muted/50 px-4 py-3 shadow-sm">
                <div className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-primary/60 animate-bounce" />
                  <div className="w-2 h-2 rounded-full bg-primary/60 animate-bounce [animation-delay:0.2s]" />
                  <div className="w-2 h-2 rounded-full bg-primary/60 animate-bounce [animation-delay:0.4s]" />
                </div>
              </div>
            </div>
          )}

          {/* Scroll anchor with extra padding so last line is never cut off */}
          <div ref={messagesEndRef} className="h-4" />
        </div>

        {/* Input area */}
        <div className="border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80 absolute bottom-0 left-0 right-0">
          <form
            onSubmit={handleSubmit}
            className="flex items-end gap-3 p-4 max-w-4xl mx-auto"
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Сұрағыңызды жазыңыз..."
              rows={1}
              className="flex-1 min-w-0 min-h-[44px] max-h-[160px] resize-none rounded-xl border border-input bg-background px-4 py-2.5 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            />
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="inline-flex items-center justify-center rounded-xl text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-11 w-11 flex-shrink-0"
            >
              <Send className="h-4 w-4" />
            </button>
          </form>
        </div>
      </div>
    </DashboardLayout>
  );
}
