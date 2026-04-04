"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDistanceToNow } from "date-fns";
import { api, ApiError } from "@/lib/api";
import { FileIcon, defaultStyles } from "react-file-icon";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { FileText, Trash2, BookOpen, Loader2, ChevronDown, ChevronRight } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ProcessingTask {
  id: number;
  status: string;
  error_message: string | null;
}

interface BookAnalysis {
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

interface Document {
  id: number;
  file_name: string;
  file_path: string;
  file_size: number;
  content_type: string;
  created_at: string;
  processing_tasks: ProcessingTask[];
  analysis: BookAnalysis | null;
}

interface PendingTask {
  task_id: number;
  file_name: string | null;
  file_size: number | null;
  status: string;
  error_message: string | null;
}

interface Chunk {
  id: string;
  chunk_metadata: {
    page_content?: string;
    work_title?: string;
    main_author?: string;
    book_title?: string;
    start_page?: number;
    end_page?: number;
    section_type?: string;
    [key: string]: unknown;
  };
}

interface Row {
  key: string;
  docId: number | null;
  taskId: number | null;
  file_name: string;
  display_name: string;
  file_size: number | null;
  content_type: string | null;
  created_at: string | null;
  status: string;
  error_message: string | null;
  analysis: BookAnalysis | null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function isActive(status: string) {
  return status === "pending" || status === "processing";
}

function displayName(file_name: string, analysis: BookAnalysis | null): string {
  const author = analysis?.metadata?.main_author?.trim();
  const title = analysis?.metadata?.book_title?.trim();
  if (author && title) return `${author} — ${title}`;
  if (title) return title;
  return file_name;
}

function fileIcon(contentType: string | null, fileName: string) {
  const ext = fileName.split(".").pop() ?? "";
  if (contentType?.includes("pdf")) return <FileIcon extension="pdf" {...defaultStyles.pdf} />;
  if (contentType?.includes("doc")) return <FileIcon extension="doc" {...defaultStyles.docx} />;
  return <FileIcon extension={ext} color="#E2E8F0" labelColor="#94A3B8" />;
}

function statusBadge(status: string, errorMsg: string | null) {
  if (status === "completed") return <Badge variant="secondary">completed</Badge>;
  if (status === "failed")
    return (
      <div className="flex flex-col gap-1">
        <Badge variant="destructive">failed</Badge>
        {errorMsg && (
          <p className="text-xs text-destructive max-w-[200px] break-words">{errorMsg}</p>
        )}
      </div>
    );
  return (
    <Badge variant="default" className="gap-1">
      <Loader2 className="h-3 w-3 animate-spin" />
      {status}
    </Badge>
  );
}

// ─── Collapsible section ──────────────────────────────────────────────────────

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
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 w-full text-left font-semibold text-xs uppercase tracking-wide text-muted-foreground mb-2 hover:text-foreground transition-colors"
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {title}
      </button>
      {open && children}
    </div>
  );
}

function WorkChunk({ chunk, idx }: { chunk: Chunk; idx: number }) {
  const [open, setOpen] = useState(false);
  const rawTitle = chunk.chunk_metadata.work_title?.trim();
  const title = rawTitle ?? `Work ${idx + 1}`;

  return (
    <div className="py-3">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-baseline justify-between gap-4 w-full text-left hover:text-foreground transition-colors"
      >
        <span className="min-w-0 flex-1 font-medium flex items-center gap-1">
          {open ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />}
          {title}
        </span>
        {chunk.chunk_metadata.start_page != null && (
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            pp. {chunk.chunk_metadata.start_page}–{chunk.chunk_metadata.end_page}
          </span>
        )}
      </button>
      {open && (
        <p className="whitespace-pre-wrap leading-relaxed text-muted-foreground mt-2 pl-4">
          {chunk.chunk_metadata.page_content ?? ""}
        </p>
      )}
    </div>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

interface DocumentListProps {
  knowledgeBaseId: number;
}

export function DocumentList({ knowledgeBaseId }: DocumentListProps) {
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<{ row: Row; chunks: Chunk[] } | null>(null);
  const [loadingModal, setLoadingModal] = useState<Record<string, boolean>>({});
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set());
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const buildRows = (documents: Document[], pendingTasks: PendingTask[]): Row[] => {
    const docRows: Row[] = documents.map((doc) => {
      const task = doc.processing_tasks[0];
      return {
        key: `doc-${doc.id}`,
        docId: doc.id,
        taskId: task?.id ?? null,
        file_name: doc.file_name,
        display_name: displayName(doc.file_name, doc.analysis),
        file_size: doc.file_size,
        content_type: doc.content_type,
        created_at: doc.created_at,
        status: task?.status ?? "completed",
        error_message: task?.error_message ?? null,
        analysis: doc.analysis,
      };
    });

    const docFileNames = new Set(documents.map((d) => d.file_name));
    const pendingRows: Row[] = pendingTasks
      .filter((t) => t.file_name && !docFileNames.has(t.file_name))
      .map((t) => ({
        key: `task-${t.task_id}`,
        docId: null,
        taskId: t.task_id,
        file_name: t.file_name ?? "Unknown",
        display_name: t.file_name ?? "Unknown",
        file_size: t.file_size,
        content_type: null,
        created_at: null,
        status: t.status,
        error_message: t.error_message,
        analysis: null,
      }));

    return [...pendingRows, ...docRows];
  };

  const fetchData = useCallback(async () => {
    try {
      const [kb, tasks] = await Promise.all([
        api.get(`/api/knowledge-base/${knowledgeBaseId}`),
        api.get(`/api/knowledge-base/${knowledgeBaseId}/tasks`),
      ]);
      const merged = buildRows(kb.documents as Document[], tasks as PendingTask[]);
      setRows(merged);
      setError(null);
      return merged;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to fetch documents");
      return null;
    } finally {
      setLoading(false);
    }
  }, [knowledgeBaseId]);

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      const merged = await fetchData();
      if (cancelled) return;
      if (merged && merged.some((r) => isActive(r.status))) {
        pollRef.current = setTimeout(tick, 3000);
      }
    };

    tick();

    return () => {
      cancelled = true;
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [fetchData]);

  // ── Actions ─────────────────────────────────────────────────────────────────

  const handleDelete = async (row: Row) => {
    setDeletingIds((s) => new Set(s).add(row.key));
    try {
      if (row.docId !== null) {
        await api.delete(`/api/knowledge-base/${knowledgeBaseId}/documents/${row.docId}`);
      } else if (row.taskId !== null) {
        await api.delete(`/api/knowledge-base/${knowledgeBaseId}/tasks/${row.taskId}`);
      }
      setRows((prev) => prev.filter((r) => r.key !== row.key));
      if (modal?.row.key === row.key) setModal(null);
    } finally {
      setDeletingIds((s) => {
        const next = new Set(s);
        next.delete(row.key);
        return next;
      });
    }
  };

  const openModal = async (row: Row) => {
    if (!row.docId) return;
    setLoadingModal((prev) => ({ ...prev, [row.key]: true }));
    try {
      const chunks: Chunk[] = await api.get(
        `/api/knowledge-base/${knowledgeBaseId}/documents/${row.docId}/chunks`
      );
      setModal({ row, chunks });
    } finally {
      setLoadingModal((prev) => ({ ...prev, [row.key]: false }));
    }
  };

  const tocEntry = modal?.row.analysis?.toc ?? null;
  const tocItems = [...(tocEntry ? [tocEntry] : []), ...(modal?.row.analysis?.works ?? [])];

  // ── Render ──────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex justify-center items-center p-8">
        <div className="space-y-4 text-center">
          <div className="w-8 h-8 border-4 border-primary/30 border-t-primary rounded-full animate-spin mx-auto" />
          <p className="text-muted-foreground animate-pulse">Loading documents…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center p-8">
        <p className="text-destructive">{error}</p>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] p-8">
        <div className="flex flex-col items-center max-w-[420px] text-center space-y-6">
          <div className="w-20 h-20 rounded-full bg-muted flex items-center justify-center">
            <FileText className="w-10 h-10 text-muted-foreground" />
          </div>
          <div className="space-y-2">
            <h3 className="text-xl font-semibold">No documents yet</h3>
            <p className="text-muted-foreground">
              Drop files above to start building your knowledge base.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Size</TableHead>
            <TableHead>Added</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => {
            const deleting = deletingIds.has(row.key);
            const modalLoading = loadingModal[row.key];

            return (
              <TableRow key={row.key}>
                <TableCell className="font-medium">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 flex-shrink-0">
                      {fileIcon(row.content_type, row.file_name)}
                    </div>
                    <span className="truncate max-w-[300px]" title={row.file_name}>
                      {row.display_name}
                    </span>
                  </div>
                </TableCell>
                <TableCell>
                  {row.file_size !== null
                    ? `${(row.file_size / 1024 / 1024).toFixed(2)} MB`
                    : "—"}
                </TableCell>
                <TableCell>
                  {row.created_at
                    ? formatDistanceToNow(
                        new Date(row.created_at.endsWith("Z") ? row.created_at : row.created_at + "Z"),
                        { addSuffix: true }
                      )
                    : "—"}
                </TableCell>
                <TableCell>{statusBadge(row.status, row.error_message)}</TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    {row.docId !== null && row.status === "completed" && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => openModal(row)}
                        title="View book content"
                      >
                        {modalLoading ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <BookOpen className="h-4 w-4" />
                        )}
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-destructive hover:text-destructive"
                      onClick={() => handleDelete(row)}
                      disabled={deleting}
                      title={row.docId ? "Delete document" : "Cancel processing"}
                    >
                      {deleting ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>

      {/* Book content modal */}
      <Dialog open={modal !== null} onOpenChange={(open) => !open && setModal(null)}>
        <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
          <DialogHeader className="pb-2">
            {modal?.row.analysis?.metadata.main_author && (
              <p className="text-sm text-muted-foreground font-medium uppercase tracking-wide">
                {modal.row.analysis.metadata.main_author}
              </p>
            )}
            <DialogTitle className="text-xl leading-tight">
              {modal?.row.analysis?.metadata.book_title || modal?.row.display_name}
            </DialogTitle>
            {(modal?.row.analysis?.metadata.year || modal?.row.analysis?.metadata.publisher) && (
              <p className="text-sm text-muted-foreground">
                {[modal.row.analysis?.metadata.year, modal.row.analysis?.metadata.publisher]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            )}
          </DialogHeader>

          <div className="overflow-y-auto flex-1 space-y-6 pr-1 text-sm">
            {/* Summary */}
            {modal?.row.analysis?.summary && (
              <Section title="Summary">
                <p className="leading-relaxed">{modal.row.analysis.summary}</p>
              </Section>
            )}

            {/* Table of contents */}
            {tocItems.length > 0 && (
              <Section title={`Table of Contents (${tocItems.length} items)`}>
                <ol className="space-y-1">
                  {tocItems.map((w, i) => (
                    <li key={i} className="flex justify-between gap-4">
                      <span className="text-foreground">{w.title}</span>
                      <span className="text-muted-foreground whitespace-nowrap text-xs mt-0.5">
                        pp. {w.start_page}–{w.end_page}
                      </span>
                    </li>
                  ))}
                </ol>
              </Section>
            )}

            {/* Works content */}
            {modal && modal.chunks.length > 0 && (
              <Section title={`Sections (${modal.chunks.length})`} defaultOpen={false}>
                <div className="divide-y">
                  {[...modal.chunks]
                    .sort((a, b) => (a.chunk_metadata.start_page ?? 0) - (b.chunk_metadata.start_page ?? 0))
                    .map((chunk, idx) => (
                      <WorkChunk key={chunk.id} chunk={chunk} idx={idx} />
                    ))}
                </div>
              </Section>
            )}

            {modal && modal.chunks.length === 0 && (
              <p className="text-muted-foreground text-center py-4">No content available.</p>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
