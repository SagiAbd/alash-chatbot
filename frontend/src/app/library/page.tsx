"use client";

import { ChangeEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { FileIcon, defaultStyles } from "react-file-icon";
import {
  Library,
  Loader2,
  LogIn,
  Trash2,
  Upload,
  UserPlus,
} from "lucide-react";
import DashboardLayout from "@/components/layout/dashboard-layout";
import { PublicDocumentViewer } from "@/components/knowledge-base/public-document-viewer";
import { AuthenticatedUser } from "@/lib/auth";
import { ApiError, api } from "@/lib/api";
import { fetchCurrentUser } from "@/lib/session";
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

interface LibraryDocument {
  id: number;
  file_name: string;
  file_size: number;
  created_at: string;
  content_type: string;
  analysis?: BookAnalysis | GlossaryAnalysis | null;
}

interface LibraryTask {
  task_id: number;
  document_id: number | null;
  file_name: string | null;
  status: string;
  error_message: string | null;
}

const TASK_STATUS_LABELS: Record<string, string> = {
  pending: "кезекте",
  processing: "өңделіп жатыр",
  completed: "аяқталды",
  failed: "сәтсіз аяқталды",
};

function fileIcon(contentType: string, fileName: string) {
  const ext = (fileName.split(".").pop() ?? "").toLowerCase();
  if (contentType.includes("pdf") || ext === "pdf") {
    return <FileIcon extension="pdf" {...defaultStyles.pdf} />;
  }
  return <FileIcon extension="docx" {...defaultStyles.docx} />;
}

export default function LibraryPage() {
  const { toast } = useToast();
  const [user, setUser] = useState<AuthenticatedUser | null | undefined>(undefined);
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
          title: "Қате",
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
      setUser(currentUser);
      if (!currentUser) {
        setLoading(false);
        return;
      }
      await loadLibrary();
    };

    void bootstrap();
  }, []);

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
        title: "Жүктеу кезекке қойылды",
        description: result.message || `${file.name} файлы өңделіп жатыр.`,
      });
      await loadLibrary();
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "Жүктеу сәтсіз аяқталды";
      toast({
        title: "Жүктеу сәтсіз аяқталды",
        description: message,
        variant: "destructive",
      });
    } finally {
      event.target.value = "";
      setUploading(false);
    }
  };

  const handleDelete = async (docId: number) => {
    if (!confirm("Бұл файлды кітапханаңыздан жойғыңыз келе ме?")) {
      return;
    }

    try {
      await api.delete(`/api/me/library/documents/${docId}`);
      setDocuments((current) => current.filter((doc) => doc.id !== docId));
      toast({
        title: "Жойылды",
        description: "Құжат кітапханаңыздан өшірілді.",
      });
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "Жою сәтсіз аяқталды";
      toast({
        title: "Жою сәтсіз аяқталды",
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
            <h1 className="text-3xl font-bold tracking-tight">Менің кітапханам</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Жеке кітаптарыңызды жүктеңіз. Чат кезінде олар ашық
              білім қорымен бірге қолданылатын болады.
            </p>
          </div>
          {user ? (
            <label className="inline-flex cursor-pointer items-center justify-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">
              <Upload className="mr-2 h-4 w-4" />
              {uploading ? "Жүктеліп жатыр..." : "Кітапты жүктеу"}
              <input
                type="file"
                accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                className="hidden"
                disabled={uploading}
                onChange={handleUpload}
              />
            </label>
          ) : (
            <Link
              href="/login?next=/library"
              className="inline-flex items-center justify-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              <LogIn className="mr-2 h-4 w-4" />
              Жүктеу үшін кіру
            </Link>
          )}
        </div>

        {user === null && (
          <div className="rounded-2xl border bg-card p-8 shadow-sm">
            <div className="mx-auto max-w-2xl text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <Library className="h-7 w-7" />
              </div>
              <h2 className="mt-4 text-2xl font-semibold">
                Менің кітапханам үшін аккаунт қажет
              </h2>
              <p className="mt-3 text-sm text-muted-foreground">
                Жеке құжаттарды жүктеп, чатта оларды ашық білім қорымен бірге
                қолдану үшін жүйеге кіріңіз немесе тіркеліңіз.
              </p>
              <div className="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
                <Link
                  href="/login?next=/library"
                  className="inline-flex items-center justify-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                >
                  <LogIn className="mr-2 h-4 w-4" />
                  Кіру
                </Link>
                <Link
                  href="/register?next=/library"
                  className="inline-flex items-center justify-center rounded-lg border px-4 py-2 text-sm font-medium hover:bg-accent"
                >
                  <UserPlus className="mr-2 h-4 w-4" />
                  Тіркелу
                </Link>
              </div>
            </div>
          </div>
        )}

        {user && tasks.length > 0 && (
          <div className="rounded-2xl border bg-card p-6 shadow-sm">
            <h2 className="text-lg font-semibold">Өңделіп жатыр</h2>
            <div className="mt-4 space-y-3">
              {tasks.map((task) => (
                <div
                  key={task.task_id}
                  className="flex items-center justify-between rounded-lg border px-4 py-3"
                >
                  <div>
                    <div className="font-medium">
                      {task.file_name || `Тапсырма #${task.task_id}`}
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
                    {TASK_STATUS_LABELS[task.status] ?? task.status}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {user && (
          <div className="rounded-2xl border bg-card p-6 shadow-sm">
            <h2 className="text-lg font-semibold">Кітаптар</h2>

            {loading ? (
              <div className="py-10 text-sm text-muted-foreground">
                Кітапхана жүктеліп жатыр...
              </div>
            ) : documents.length === 0 ? (
              <div className="py-10 text-sm text-muted-foreground">
                Жеке кітапханаңыз әзірге бос...
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
                    <div className="flex items-center gap-2">
                      <PublicDocumentViewer
                        document={document}
                        chunksPath={`/api/me/library/documents/${document.id}/chunks`}
                      />
                      <button
                        onClick={() => handleDelete(document.id)}
                        className="rounded-lg p-2 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                        aria-label={`${document.file_name} файлын жою`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
