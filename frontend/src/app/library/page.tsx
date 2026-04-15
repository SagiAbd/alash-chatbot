"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { FileIcon, defaultStyles } from "react-file-icon";
import { Loader2, Trash2, Upload } from "lucide-react";
import DashboardLayout from "@/components/layout/dashboard-layout";
import { ApiError, api } from "@/lib/api";
import { fetchCurrentUser } from "@/lib/session";
import { useToast } from "@/components/ui/use-toast";

interface LibraryDocument {
  id: number;
  file_name: string;
  file_size: number;
  created_at: string;
  content_type: string;
}

interface LibraryTask {
  task_id: number;
  document_id: number | null;
  file_name: string | null;
  status: string;
  error_message: string | null;
}

function fileIcon(contentType: string, fileName: string) {
  const ext = (fileName.split(".").pop() ?? "").toLowerCase();
  if (contentType.includes("pdf") || ext === "pdf") {
    return <FileIcon extension="pdf" {...defaultStyles.pdf} />;
  }
  return <FileIcon extension="docx" {...defaultStyles.docx} />;
}

export default function LibraryPage() {
  const router = useRouter();
  const { toast } = useToast();
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [tasks, setTasks] = useState<LibraryTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  const hasActiveTasks = useMemo(
    () => tasks.some((task) => task.status === "pending" || task.status === "processing"),
    [tasks],
  );

  const loadLibrary = async () => {
    try {
      const [docs, currentTasks] = await Promise.all([
        api.get("/api/me/library"),
        api.get("/api/me/library/tasks"),
      ]);
      setDocuments(docs as LibraryDocument[]);
      setTasks(currentTasks as LibraryTask[]);
    } catch (error) {
      if (error instanceof ApiError) {
        toast({
          title: "Error",
          description: error.message,
          variant: "destructive",
        });
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const bootstrap = async () => {
      const currentUser = await fetchCurrentUser();
      if (!currentUser) {
        router.replace("/login?next=/library");
        return;
      }
      await loadLibrary();
    };

    void bootstrap();
  }, [router]);

  useEffect(() => {
    if (!hasActiveTasks) {
      return;
    }

    const interval = window.setInterval(() => {
      void loadLibrary();
    }, 3000);

    return () => window.clearInterval(interval);
  }, [hasActiveTasks]);

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const result = (await api.post("/api/me/library/upload", formData)) as {
        message?: string;
      };
      toast({
        title: "Upload queued",
        description: result.message || `${file.name} is being processed.`,
      });
      await loadLibrary();
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "Upload failed";
      toast({
        title: "Upload failed",
        description: message,
        variant: "destructive",
      });
    } finally {
      event.target.value = "";
      setUploading(false);
    }
  };

  const handleDelete = async (docId: number) => {
    if (!confirm("Delete this file from your library?")) {
      return;
    }

    try {
      await api.delete(`/api/me/library/documents/${docId}`);
      setDocuments((current) => current.filter((doc) => doc.id !== docId));
      toast({
        title: "Deleted",
        description: "The document was removed from your library.",
      });
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "Delete failed";
      toast({
        title: "Delete failed",
        description: message,
        variant: "destructive",
      });
    }
  };

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex flex-col gap-4 rounded-2xl border bg-card p-6 shadow-sm sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">My Library</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Upload personal `.docx` and `.pdf` files. These are searched
              alongside the public knowledge base when you chat.
            </p>
          </div>
          <label className="inline-flex cursor-pointer items-center justify-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">
            <Upload className="mr-2 h-4 w-4" />
            {uploading ? "Uploading..." : "Upload file"}
            <input
              type="file"
              accept=".docx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              className="hidden"
              disabled={uploading}
              onChange={handleUpload}
            />
          </label>
        </div>

        {tasks.length > 0 && (
          <div className="rounded-2xl border bg-card p-6 shadow-sm">
            <h2 className="text-lg font-semibold">Processing</h2>
            <div className="mt-4 space-y-3">
              {tasks.map((task) => (
                <div
                  key={task.task_id}
                  className="flex items-center justify-between rounded-lg border px-4 py-3"
                >
                  <div>
                    <div className="font-medium">
                      {task.file_name || `Task #${task.task_id}`}
                    </div>
                    {task.error_message && (
                      <div className="mt-1 text-sm text-destructive">
                        {task.error_message}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    {(task.status === "pending" || task.status === "processing") && (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    )}
                    {task.status}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="rounded-2xl border bg-card p-6 shadow-sm">
          <h2 className="text-lg font-semibold">Documents</h2>

          {loading ? (
            <div className="py-10 text-sm text-muted-foreground">Loading library...</div>
          ) : documents.length === 0 ? (
            <div className="py-10 text-sm text-muted-foreground">
              No personal documents yet.
            </div>
          ) : (
            <div className="mt-4 space-y-3">
              {documents.map((document) => (
                <div
                  key={document.id}
                  className="flex items-center justify-between rounded-xl border px-4 py-4"
                >
                  <div className="flex min-w-0 items-center gap-4">
                    <div className="h-10 w-10 shrink-0">
                      {fileIcon(document.content_type, document.file_name)}
                    </div>
                    <div className="min-w-0">
                      <div className="truncate font-medium">{document.file_name}</div>
                      <div className="text-sm text-muted-foreground">
                        {new Date(document.created_at).toLocaleString()} ·{" "}
                        {(document.file_size / 1024 / 1024).toFixed(2)} MB
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(document.id)}
                    className="rounded-lg p-2 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    aria-label={`Delete ${document.file_name}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
