import React, {
  useMemo,
  useState,
  useRef,
  useEffect,
  ClassAttributes,
} from "react";
import { AnchorHTMLAttributes } from "react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { Divider } from "@/components/ui/divider";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import rehypeRaw from "rehype-raw";
import { api } from "@/lib/api";
import { FileIcon } from "react-file-icon";

interface Citation {
  id: number;
  text: string;
  metadata: Record<string, any>;
}

interface KnowledgeBaseInfo {
  name: string;
}

interface DocumentInfo {
  file_name: string;
  knowledge_base: KnowledgeBaseInfo;
}

interface CitationInfo {
  knowledge_base: KnowledgeBaseInfo;
  document: DocumentInfo;
}

const BRACKETED_URL_RE = /\[(https?:\/\/[^\s\]]+)\]/g;

const normalizeBracketedUrls = (markdown: string): string => {
  return markdown.replace(BRACKETED_URL_RE, (_match, rawUrl: string) => {
    return `[${rawUrl}](${rawUrl})`;
  });
};

export const Answer = ({
  markdown,
  citations = [],
  isStreaming = false,
}: {
  markdown: string;
  citations?: Citation[];
  isStreaming?: boolean;
}) => {
  const [citationInfoMap, setCitationInfoMap] = useState<
    Record<string, CitationInfo>
  >({});
  const animatedMarkdown = useStreamingText(markdown, isStreaming);

  const processedMarkdown = useMemo(() => {
    return normalizeBracketedUrls(animatedMarkdown);
  }, [animatedMarkdown]);

  useEffect(() => {
    const fetchCitationInfo = async () => {
      const infoMap: Record<string, CitationInfo> = {};

      for (const citation of citations) {
        const { kb_id, document_id } = citation.metadata;
        if (!kb_id || !document_id) continue;

        const key = `${kb_id}-${document_id}`;
        if (infoMap[key]) continue;

        try {
          const [kb, doc] = await Promise.all([
            api.get(`/api/knowledge-base/${kb_id}`),
            api.get(`/api/knowledge-base/${kb_id}/documents/${document_id}`),
          ]);

          infoMap[key] = {
            knowledge_base: {
              name: kb.name,
            },
            document: {
              file_name: doc.file_name,
              knowledge_base: {
                name: kb.name,
              },
            },
          };
        } catch (error) {
          console.error("Failed to fetch citation info:", error);
        }
      }

      setCitationInfoMap(infoMap);
    };

    if (citations.length > 0) {
      fetchCitationInfo();
    }
  }, [citations]);

  const CitationLink = useMemo(
    () =>
      (
        props: ClassAttributes<HTMLAnchorElement> &
          AnchorHTMLAttributes<HTMLAnchorElement>
      ) => {
        const citationId = props.href?.match(/^(\d+)$/)?.[1];
        const citation = citationId
          ? citations[parseInt(citationId) - 1]
          : null;

        if (!citation) {
          return <a>[{props.href}]</a>;
        }

        const citationInfo =
          citationInfoMap[
            `${citation.metadata.kb_id}-${citation.metadata.document_id}`
          ];

        return (
          <Popover>
            <PopoverTrigger asChild>
              <a
                {...props}
                href="#"
                role="button"
                className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs font-medium text-blue-600 bg-blue-50 rounded hover:bg-blue-100 transition-colors relative"
              >
                <span className="absolute -top-3 -right-1">[{props.href}]</span>
              </a>
            </PopoverTrigger>
            <PopoverContent
              side="top"
              align="start"
              className="max-w-2xl w-[calc(100vw-100px)] p-4 rounded-lg shadow-lg"
            >
              <div className="text-sm space-y-3">
                {citationInfo && (
                  <div className="flex items-center gap-2 text-xs font-medium text-gray-700 bg-gray-50 p-2 rounded">
                    <div className="w-5 h-5 flex items-center justify-center">
                      <FileIcon
                        extension={
                          citationInfo.document.file_name.split(".").pop() || ""
                        }
                        color="#E2E8F0"
                        labelColor="#94A3B8"
                      />
                    </div>
                    <span className="truncate">
                      {citationInfo.knowledge_base.name} /{" "}
                      {citationInfo.document.file_name}
                    </span>
                  </div>
                )}
                <Divider />
                <p className="text-gray-700 leading-relaxed">{citation.text}</p>
                <Divider />
                {Object.keys(citation.metadata).length > 0 && (
                  <div className="text-xs text-gray-500 bg-gray-50 p-2 rounded">
                    <div className="font-medium mb-2">Debug Info:</div>
                    <div className="space-y-1">
                      {Object.entries(citation.metadata).map(([key, value]) => (
                        <div key={key} className="flex">
                          <span className="font-medium min-w-[100px]">
                            {key}:
                          </span>
                          <span className="text-gray-600">{String(value)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </PopoverContent>
          </Popover>
        );
      },
    [citations, citationInfoMap]
  );

  if (!markdown) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="max-w-sm h-4 bg-zinc-200" />
        <Skeleton className="max-w-lg h-4 bg-zinc-200" />
        <Skeleton className="max-w-2xl h-4 bg-zinc-200" />
        <Skeleton className="max-w-lg h-4 bg-zinc-200" />
        <Skeleton className="max-w-xl h-4 bg-zinc-200" />
      </div>
    );
  }

  return (
    <div className="prose prose-sm max-w-full prose-table:my-3 prose-pre:my-2">
      <Markdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, rehypeHighlight]}
        components={{
          a: CitationLink,
          table: ({ children, ...props }) => (
            <div className="overflow-x-auto my-3 rounded-lg border border-border">
              <table className="min-w-full text-sm" {...props}>
                {children}
              </table>
            </div>
          ),
          thead: ({ children, ...props }) => (
            <thead className="bg-muted/70 text-left" {...props}>
              {children}
            </thead>
          ),
          th: ({ children, ...props }) => (
            <th
              className="px-3 py-2 font-semibold text-xs uppercase tracking-wider border-b border-border"
              {...props}
            >
              {children}
            </th>
          ),
          td: ({ children, ...props }) => (
            <td className="px-3 py-2 border-b border-border/50" {...props}>
              {children}
            </td>
          ),
          tr: ({ children, ...props }) => (
            <tr className="even:bg-muted/30 transition-colors" {...props}>
              {children}
            </tr>
          ),
          blockquote: ({ children, ...props }) => (
            <blockquote
              className="border-l-4 border-primary/30 bg-muted/40 rounded-r-lg px-4 py-2 my-3 text-muted-foreground italic"
              {...props}
            >
              {children}
            </blockquote>
          ),
          pre: ({ children, ...props }) => (
            <pre
              className="bg-[#1e1e2e] text-[#cdd6f4] rounded-xl p-4 my-3 overflow-x-auto text-sm leading-relaxed"
              {...props}
            >
              {children}
            </pre>
          ),
          code: ({ children, className, ...props }) => {
            const isInline = !className;
            if (isInline) {
              return (
                <code
                  className="bg-muted px-1.5 py-0.5 rounded-md text-sm font-mono"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return <code className={className} {...props}>{children}</code>;
          },
          ul: ({ children, ...props }) => (
            <ul className="list-disc pl-5 my-2 space-y-1" {...props}>
              {children}
            </ul>
          ),
          ol: ({ children, ...props }) => (
            <ol className="list-decimal pl-5 my-2 space-y-1" {...props}>
              {children}
            </ol>
          ),
          hr: () => <hr className="my-4 border-border" />,
        }}
      >
        {processedMarkdown}
      </Markdown>
    </div>
  );
};

function useStreamingText(text: string, isStreaming: boolean): string {
  const [displayed, setDisplayed] = useState(isStreaming ? "" : text);
  const displayedLenRef = useRef(isStreaming ? 0 : text.length);
  const targetRef = useRef(text);
  const rafRef = useRef<number>(0);
  const prevTimeRef = useRef(0);

  targetRef.current = text;

  useEffect(() => {
    if (isStreaming && displayedLenRef.current > text.length) {
      displayedLenRef.current = 0;
      setDisplayed("");
    }
  }, [isStreaming, text.length]);

  useEffect(() => {
    if (!isStreaming) {
      cancelAnimationFrame(rafRef.current);
      displayedLenRef.current = text.length;
      setDisplayed(text);
      prevTimeRef.current = 0;
      return;
    }

    const tick = (now: number) => {
      if (!prevTimeRef.current) prevTimeRef.current = now;
      const dt = now - prevTimeRef.current;
      prevTimeRef.current = now;

      const currentLen = displayedLenRef.current;
      const target = targetRef.current;
      const gap = target.length - currentLen;

      if (gap > 0) {
        // Adaptive rate: faster when buffer is large to avoid falling behind
        const rate = gap > 200 ? 0.5 : gap > 50 ? 0.15 : 0.06;
        const chars = Math.max(1, Math.round(dt * rate));
        const newLen = Math.min(target.length, currentLen + chars);
        displayedLenRef.current = newLen;
        setDisplayed(target.slice(0, newLen));
      }

      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(rafRef.current);
      prevTimeRef.current = 0;
    };
  }, [isStreaming]); // eslint-disable-line react-hooks/exhaustive-deps

  return displayed;
}
