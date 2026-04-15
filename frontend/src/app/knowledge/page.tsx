"use client";

import { ChangeEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { FileIcon, defaultStyles } from "react-file-icon";
import {
  Check,
  Plus,
  Search,
  Settings,
  Trash2,
  Upload,
} from "lucide-react";
import DashboardLayout from "@/components/layout/dashboard-layout";
import { AuthenticatedUser } from "@/lib/auth";
import { ApiError, api } from "@/lib/api";
import { fetchCurrentUser, isAdmin } from "@/lib/session";
import { useToast } from "@/components/ui/use-toast";

interface KnowledgeDocument {
  id: number;
  file_name: string;
  content_type: string;
}

interface KnowledgeBase {
  id: number;
  name: string;
  description: string;
  created_at?: string;
  documents: KnowledgeDocument[];
}

interface AppSettings {
  public_kb_id: number | null;
}

function renderFileIcon(contentType: string, fileName: string) {
  const ext = (fileName.split(".").pop() ?? "").toLowerCase();
  if (contentType.includes("pdf") || ext === "pdf") {
    return <FileIcon extension="pdf" {...defaultStyles.pdf} />;
  }
  if (ext === "docx") {
    return <FileIcon extension="docx" {...defaultStyles.docx} />;
  }
  if (ext === "xlsx") {
    return <FileIcon extension="xlsx" {...defaultStyles.xlsx} />;
  }
  return <FileIcon extension={ext} color="#E2E8F0" labelColor="#94A3B8" />;
}

export default function KnowledgePage() {
  const { toast } = useToast();
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const [user, setUser] = useState<AuthenticatedUser | null | undefined>(
    undefined,
  );
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [publicKbId, setPublicKbId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [settingPublicId, setSettingPublicId] = useState<number | null>(null);

  const loadData = async (currentUser: AuthenticatedUser | null) => {
    try {
      if (isAdmin(currentUser)) {
        const [kbs, settings] = await Promise.all([
          api.get("/api/knowledge-base"),
          api.get("/api/settings"),
        ]);
        setKnowledgeBases(kbs as KnowledgeBase[]);
        setPublicKbId((settings as AppSettings).public_kb_id);
      } else {
        const kb = (await api.get("/api/public/knowledge-base")) as KnowledgeBase;
        setKnowledgeBases([kb]);
      }
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
      setUser(currentUser);
      await loadData(currentUser);
    };

    void bootstrap();
  }, []);

  const handleSetPublic = async (id: number) => {
    setSettingPublicId(id);
    try {
      const data = (await api.post(
        `/api/knowledge-base/${id}/set-public-chatbot`,
      )) as { public_kb_id: number };
      setPublicKbId(data.public_kb_id);
      toast({
        title: "Saved",
        description: "Main public knowledge base updated.",
      });
    } catch (error) {
      if (error instanceof ApiError) {
        toast({
          title: "Error",
          description: error.message,
          variant: "destructive",
        });
      }
    } finally {
      setSettingPublicId(null);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this knowledge base?")) {
      return;
    }

    try {
      await api.delete(`/api/knowledge-base/${id}`);
      setKnowledgeBases((current) => current.filter((kb) => kb.id !== id));
      if (publicKbId === id) {
        setPublicKbId(null);
      }
      toast({
        title: "Deleted",
        description: "Knowledge base deleted successfully.",
      });
    } catch (error) {
      if (error instanceof ApiError) {
        toast({
          title: "Error",
          description: error.message,
          variant: "destructive",
        });
      }
    }
  };

  const handleImport = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    setImporting(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      await api.post("/api/knowledge-base/import", formData);
      await loadData(user ?? null);
      toast({
        title: "Imported",
        description: `Imported "${file.name}" successfully.`,
      });
    } catch (error) {
      if (error instanceof ApiError) {
        toast({
          title: "Error",
          description: error.message,
          variant: "destructive",
        });
      }
    } finally {
      event.target.value = "";
      setImporting(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Knowledge Base</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {isAdmin(user ?? null)
                ? "Manage the public knowledge base and your admin tools."
                : "Browse the public knowledge base used by the shared chat."}
            </p>
          </div>

          {isAdmin(user ?? null) && (
            <div className="flex items-center gap-3">
              <input
                ref={importInputRef}
                type="file"
                accept=".json,application/json"
                className="hidden"
                onChange={handleImport}
              />
              <button
                type="button"
                onClick={() => importInputRef.current?.click()}
                disabled={importing}
                className="inline-flex items-center justify-center rounded-md border px-4 py-2 text-sm font-medium hover:bg-accent disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Upload className="mr-2 h-4 w-4" />
                {importing ? "Importing..." : "Import KB"}
              </button>
              <Link
                href="/knowledge/new"
                className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
              >
                <Plus className="mr-2 h-4 w-4" />
                New Knowledge Base
              </Link>
            </div>
          )}
        </div>

        {loading ? (
          <div className="rounded-2xl border bg-card p-8 text-sm text-muted-foreground shadow-sm">
            Loading knowledge bases...
          </div>
        ) : (
          <div className="grid gap-6">
            {knowledgeBases.map((kb) => (
              <div key={kb.id} className="space-y-4 rounded-2xl border bg-card p-6 shadow-sm">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <h2 className="text-xl font-semibold">{kb.name}</h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {kb.description || "No description provided."}
                    </p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      {kb.documents.length} documents
                      {kb.created_at
                        ? ` · ${new Date(kb.created_at).toLocaleDateString()}`
                        : ""}
                    </p>
                    {(publicKbId === kb.id || !isAdmin(user ?? null)) && (
                      <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">
                        <Check className="h-3.5 w-3.5" />
                        Main public knowledge base
                      </div>
                    )}
                  </div>

                  {isAdmin(user ?? null) && (
                    <div className="flex flex-wrap justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => handleSetPublic(kb.id)}
                        disabled={settingPublicId === kb.id || publicKbId === kb.id}
                        className="inline-flex items-center justify-center rounded-md border px-3 py-2 text-xs font-medium hover:bg-accent disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {publicKbId === kb.id
                          ? "Public chatbot KB"
                          : settingPublicId === kb.id
                          ? "Saving..."
                          : "Set as public chatbot KB"}
                      </button>
                      <Link
                        href={`/knowledge/${kb.id}`}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-secondary"
                      >
                        <Settings className="h-4 w-4" />
                      </Link>
                      <Link
                        href={`/test-retrieval/${kb.id}`}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-secondary"
                      >
                        <Search className="h-4 w-4" />
                      </Link>
                      <button
                        onClick={() => handleDelete(kb.id)}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-destructive/10 hover:bg-destructive/20"
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </button>
                    </div>
                  )}
                </div>

                {kb.documents.length > 0 ? (
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {kb.documents.map((document) => (
                      <div
                        key={document.id}
                        className="flex items-center gap-3 rounded-xl border px-4 py-3"
                      >
                        <div className="h-10 w-10 shrink-0">
                          {renderFileIcon(document.content_type, document.file_name)}
                        </div>
                        <div className="min-w-0">
                          <div className="truncate font-medium">{document.file_name}</div>
                          <div className="text-sm text-muted-foreground">
                            {document.content_type}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed px-4 py-6 text-sm text-muted-foreground">
                    No documents yet.
                  </div>
                )}

                <div className="pt-2">
                  <Link
                    href={`/knowledge/${kb.id}`}
                    className="inline-flex items-center justify-center rounded-md border px-3 py-2 text-sm font-medium hover:bg-accent"
                  >
                    Open knowledge base
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
