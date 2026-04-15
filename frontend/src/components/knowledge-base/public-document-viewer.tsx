"use client";

import { useState } from "react";
import { BookOpen, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/use-toast";

interface BookAnalysis {
  type?: undefined;
  summary: string;
  metadata: {
    book_title: string;
    main_author: string;
    publisher: string;
    year: string;
  };
  toc?: { title: string; start_page: number; end_page: number } | null;
  works: Array<{ title: string; start_page: number; end_page: number }>;
}

interface GlossaryAnalysis {
  type: "glossary";
  term_count: number;
  authors: string[];
  fields: string[];
  title?: string | null;
  source_author?: string | null;
}

type DocumentAnalysis = BookAnalysis | GlossaryAnalysis | null;

interface Chunk {
  id: string;
  chunk_metadata: {
    page_content?: string;
    work_title?: string;
    start_page?: number;
    end_page?: number;
    alash_term?: string;
    modern_term?: string;
    field?: string;
    author?: string;
    alash_definition?: string;
    context?: string;
  };
}

interface PublicDocument {
  id: number;
  file_name: string;
  content_type: string;
  created_at: string;
  analysis?: DocumentAnalysis;
}

function isGlossary(analysis: DocumentAnalysis): analysis is GlossaryAnalysis {
  return (analysis as GlossaryAnalysis | null)?.type === "glossary";
}

function getGlossaryDisplayTitle(
  document: PublicDocument,
  analysis: GlossaryAnalysis,
): string {
  const glossaryTitle = analysis.title?.trim();
  const glossaryAuthor =
    analysis.source_author?.trim() || analysis.authors?.[0]?.trim();

  if (!glossaryTitle) {
    return document.file_name;
  }

  return glossaryAuthor
    ? `${glossaryAuthor} - ${glossaryTitle}`
    : glossaryTitle;
}

function Section({
  title,
  defaultOpen = true,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        onClick={() => setOpen((current) => !current)}
        className="mb-2 flex w-full items-center gap-1 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground transition-colors hover:text-foreground"
      >
        {open ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        {title}
      </button>
      {open && children}
    </div>
  );
}

function WorkChunk({ chunk, idx }: { chunk: Chunk; idx: number }) {
  const [open, setOpen] = useState(false);
  const title = chunk.chunk_metadata.work_title?.trim() || `Work ${idx + 1}`;

  return (
    <div className="py-3">
      <button
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-baseline justify-between gap-4 text-left transition-colors hover:text-foreground"
      >
        <span className="flex min-w-0 flex-1 items-center gap-1 font-medium">
          {open ? (
            <ChevronDown className="h-3 w-3 shrink-0" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0" />
          )}
          {title}
        </span>
        {chunk.chunk_metadata.start_page != null && (
          <span className="whitespace-nowrap text-xs text-muted-foreground">
            pp. {chunk.chunk_metadata.start_page}–
            {chunk.chunk_metadata.end_page}
          </span>
        )}
      </button>
      {open && (
        <p className="mt-2 whitespace-pre-wrap pl-4 leading-relaxed text-muted-foreground">
          {chunk.chunk_metadata.page_content ?? ""}
        </p>
      )}
    </div>
  );
}

function TermChunk({ chunk, idx }: { chunk: Chunk; idx: number }) {
  const [open, setOpen] = useState(false);
  const metadata = chunk.chunk_metadata;
  const label = metadata.alash_term || `Term ${idx + 1}`;

  return (
    <div className="py-2">
      <button
        onClick={() => setOpen((current) => !current)}
        className="flex w-full items-baseline justify-between gap-4 text-left transition-colors hover:text-foreground"
      >
        <span className="flex min-w-0 flex-1 items-center gap-1 font-medium">
          {open ? (
            <ChevronDown className="h-3 w-3 shrink-0" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0" />
          )}
          {label}
          {metadata.modern_term && metadata.modern_term !== label && (
            <span className="ml-1 font-normal text-muted-foreground">
              / {metadata.modern_term}
            </span>
          )}
        </span>
        {metadata.field && (
          <span className="whitespace-nowrap text-xs text-muted-foreground">
            {metadata.field}
          </span>
        )}
      </button>
      {open && (
        <div className="mt-2 space-y-1 pl-4 text-muted-foreground">
          {metadata.author && (
            <p>
              <span className="font-medium text-foreground">Автор:</span>{" "}
              {metadata.author}
            </p>
          )}
          {metadata.alash_definition && (
            <p>
              <span className="font-medium text-foreground">Анықтама:</span>{" "}
              {metadata.alash_definition}
            </p>
          )}
          {metadata.context && (
            <p>
              <span className="font-medium text-foreground">Контекст:</span>{" "}
              {metadata.context}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function PublicDocumentViewer({
  document,
}: {
  document: PublicDocument;
}) {
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [chunks, setChunks] = useState<Chunk[]>([]);

  const handleOpen = async () => {
    setOpen(true);
    if (chunks.length > 0 || loading) {
      return;
    }

    setLoading(true);
    try {
      const data = (await api.get(
        `/api/public/knowledge-base/documents/${document.id}/chunks`,
      )) as Chunk[];
      setChunks(data);
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "Бұл құжатты жүктеу мүмкін болмады.";
      toast({
        title: "Құжат ашылмады",
        description: message,
        variant: "destructive",
      });
      setOpen(false);
    } finally {
      setLoading(false);
    }
  };

  const analysis = document.analysis ?? null;
  const bookAnalysis =
    analysis && !isGlossary(analysis) ? (analysis as BookAnalysis) : null;
  const tocEntry = bookAnalysis?.toc ?? null;
  const tocItems = [...(tocEntry ? [tocEntry] : []), ...(bookAnalysis?.works ?? [])];

  return (
    <>
      <Button variant="outline" size="sm" onClick={handleOpen} className="gap-2">
        <BookOpen className="h-4 w-4" />
        Ашу
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="flex max-h-[85vh] max-w-3xl flex-col">
          {isGlossary(analysis) ? (
            <>
              <DialogHeader className="pb-2">
                <DialogTitle className="text-xl leading-tight">
                  {getGlossaryDisplayTitle(document, analysis)}
                </DialogTitle>
                <p className="text-sm text-muted-foreground">
                  {analysis.term_count} термин
                  {analysis.fields.length > 0 &&
                    ` · ${analysis.fields.slice(0, 4).join(", ")}`}
                </p>
              </DialogHeader>

              <div className="flex-1 overflow-y-auto pr-1 text-sm">
                {loading ? (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Глоссарий жүктеліп жатыр...
                  </div>
                ) : chunks.length > 0 ? (
                  <Section title={`Терминдер (${chunks.length})`}>
                    <div className="divide-y">
                      {chunks.map((chunk, idx) => (
                        <TermChunk key={chunk.id} chunk={chunk} idx={idx} />
                      ))}
                    </div>
                  </Section>
                ) : (
                  <p className="text-muted-foreground">Глоссарий мазмұны табылмады.</p>
                )}
              </div>
            </>
          ) : (
            <>
              <DialogHeader className="space-y-2 border-b pb-4">
                {bookAnalysis?.metadata?.main_author && (
                  <p className="text-sm font-medium text-muted-foreground">
                    {bookAnalysis.metadata.main_author}
                  </p>
                )}
                <DialogTitle className="text-2xl leading-tight">
                  {bookAnalysis?.metadata?.book_title || document.file_name}
                </DialogTitle>
                {(bookAnalysis?.metadata?.year ||
                  bookAnalysis?.metadata?.publisher) && (
                  <p className="text-sm text-muted-foreground">
                    {[bookAnalysis?.metadata?.year, bookAnalysis?.metadata?.publisher]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                )}
              </DialogHeader>

              <div className="flex-1 space-y-6 overflow-y-auto pr-1 text-sm">
                {bookAnalysis?.summary && (
                  <Section title="Summary">
                    <p className="leading-relaxed">{bookAnalysis.summary}</p>
                  </Section>
                )}

                {tocItems.length > 0 && (
                  <Section title="Contents" defaultOpen={false}>
                    <div className="space-y-2">
                      {tocItems.map((item, index) => (
                        <div
                          key={`${item.title}-${index}`}
                          className="flex items-center justify-between gap-4 text-sm"
                        >
                          <span className="min-w-0 flex-1 truncate">
                            {item.title}
                          </span>
                          <span className="whitespace-nowrap text-xs text-muted-foreground">
                            pp. {item.start_page}–{item.end_page}
                          </span>
                        </div>
                      ))}
                    </div>
                  </Section>
                )}

                {loading ? (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading document...
                  </div>
                ) : chunks.length > 0 ? (
                  <Section title={`Sections (${chunks.length})`} defaultOpen={false}>
                    <div className="divide-y">
                      {[...chunks]
                        .sort(
                          (left, right) =>
                            (left.chunk_metadata.start_page ?? 0) -
                            (right.chunk_metadata.start_page ?? 0),
                        )
                        .map((chunk, idx) => (
                          <WorkChunk key={chunk.id} chunk={chunk} idx={idx} />
                        ))}
                    </div>
                  </Section>
                ) : (
                  <p className="text-muted-foreground">No document content found.</p>
                )}
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
