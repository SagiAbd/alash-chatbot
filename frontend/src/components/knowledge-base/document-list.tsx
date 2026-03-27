"use client";

import { useEffect, useRef, useState, useCallback } from "react";
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
import { FileText, Trash2, List, Loader2 } from "lucide-react";
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

interface Document {
  id: number;
  file_name: string;
  file_path: string;
  file_size: number;
  content_type: string;
  created_at: string;
  processing_tasks: ProcessingTask[];
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
  chunk_metadata: { page_content?: string; [key: string]: unknown };
}

// Unified row shown in the table
interface Row {
  key: string;
  docId: number | null; // null = pending task not yet a document
  taskId: number | null;
  file_name: string;
  file_size: number | null;
  content_type: string | null;
  created_at: string | null;
  status: string;
  error_message: string | null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function isActive(status: string) {
  return status === "pending" || status === "processing";
}

function fileIcon(contentType: string | null, fileName: string) {
  const ct = contentType?.toLowerCase() ?? "";
  const ext = fileName.split(".").pop() ?? "";
  if (ct.includes("pdf")) return <FileIcon extension="pdf" {...defaultStyles.pdf} />;
  if (ct.includes("doc")) return <FileIcon extension="doc" {...defaultStyles.docx} />;
  if (ct.includes("txt")) return <FileIcon extension="txt" {...defaultStyles.txt} />;
  if (ct.includes("md") || ext === "md") return <FileIcon extension="md" {...defaultStyles.md} />;
  return <FileIcon extension={ext} color="#E2E8F0" labelColor="#94A3B8" />;
}

function statusBadge(status: string) {
  if (status === "completed")
    return <Badge variant="secondary">{status}</Badge>;
  if (status === "failed")
    return <Badge variant="destructive">{status}</Badge>;
  return (
    <Badge variant="default" className="gap-1">
      <Loader2 className="h-3 w-3 animate-spin" />
      {status}
    </Badge>
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
  const [chunkModal, setChunkModal] = useState<{ docId: number; fileName: string; chunks: Chunk[] } | null>(null);
  const [loadingChunks, setLoadingChunks] = useState<Record<number, boolean>>({});
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
        file_size: doc.file_size,
        content_type: doc.content_type,
        created_at: doc.created_at,
        status: task?.status ?? "completed",
        error_message: task?.error_message ?? null,
      };
    });

    // Pending tasks that haven't been linked to a Document yet
    const docFileNames = new Set(documents.map((d) => d.file_name));
    const pendingRows: Row[] = pendingTasks
      .filter((t) => t.file_name && !docFileNames.has(t.file_name))
      .map((t) => ({
        key: `task-${t.task_id}`,
        docId: null,
        taskId: t.task_id,
        file_name: t.file_name ?? "Unknown",
        file_size: t.file_size,
        content_type: null,
        created_at: null,
        status: t.status,
        error_message: t.error_message,
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

  // Poll while any row is active
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
    if (!row.docId) return; // can't delete a still-pending task
    setDeletingIds((s) => new Set(s).add(row.key));
    try {
      await api.delete(`/api/knowledge-base/${knowledgeBaseId}/documents/${row.docId}`);
      setRows((prev) => prev.filter((r) => r.key !== row.key));
      if (chunkModal?.docId === row.docId) setChunkModal(null);
    } finally {
      setDeletingIds((s) => {
        const next = new Set(s);
        next.delete(row.key);
        return next;
      });
    }
  };

  const openChunks = async (row: Row) => {
    if (!row.docId) return;
    setLoadingChunks((prev) => ({ ...prev, [row.docId!]: true }));
    try {
      const chunks: Chunk[] = await api.get(
        `/api/knowledge-base/${knowledgeBaseId}/documents/${row.docId}/chunks`
      );
      setChunkModal({ docId: row.docId, fileName: row.file_name, chunks });
    } finally {
      setLoadingChunks((prev) => ({ ...prev, [row.docId!]: false }));
    }
  };

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
            <TableHead>Created</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => {
            const chunksLoading = row.docId !== null && loadingChunks[row.docId];
            const deleting = deletingIds.has(row.key);

            return (
              <TableRow key={row.key}>
                <TableCell className="font-medium">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 flex-shrink-0">
                      {fileIcon(row.content_type, row.file_name)}
                    </div>
                    <span className="truncate max-w-[280px]">{row.file_name}</span>
                  </div>
                </TableCell>
                <TableCell>
                  {row.file_size !== null
                    ? `${(row.file_size / 1024 / 1024).toFixed(2)} MB`
                    : "—"}
                </TableCell>
                <TableCell>
                  {row.created_at
                    ? formatDistanceToNow(new Date(row.created_at), { addSuffix: true })
                    : "—"}
                </TableCell>
                <TableCell>{statusBadge(row.status)}</TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    {row.docId !== null && row.status === "completed" && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => openChunks(row)}
                        title="View chunks"
                      >
                        {chunksLoading ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <List className="h-4 w-4" />
                        )}
                      </Button>
                    )}
                    {row.docId !== null && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-destructive hover:text-destructive"
                        onClick={() => handleDelete(row)}
                        disabled={deleting}
                        title="Delete document"
                      >
                        {deleting ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>

      {/* Chunk viewer modal */}
      <Dialog open={chunkModal !== null} onOpenChange={(open) => !open && setChunkModal(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="truncate pr-6">{chunkModal?.fileName}</DialogTitle>
          </DialogHeader>
          <div className="overflow-y-auto flex-1 divide-y text-sm pr-1">
            {chunkModal?.chunks.length === 0 && (
              <p className="text-muted-foreground py-4 text-center">No chunks found.</p>
            )}
            {chunkModal?.chunks.map((chunk, idx) => (
              <div key={chunk.id} className="py-4">
                <p className="text-xs text-muted-foreground mb-2 font-mono">
                  Chunk {idx + 1} of {chunkModal.chunks.length}
                </p>
                <p className="whitespace-pre-wrap leading-relaxed">
                  {chunk.chunk_metadata?.page_content ?? JSON.stringify(chunk.chunk_metadata)}
                </p>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
