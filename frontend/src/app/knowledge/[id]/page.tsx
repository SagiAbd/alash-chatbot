"use client";

import { useEffect, useState } from "react";
import AdminKnowledgeBasePage from "@/app/dashboard/knowledge/[id]/page";
import DashboardLayout from "@/components/layout/dashboard-layout";
import { AuthenticatedUser } from "@/lib/auth";
import { ApiError, api } from "@/lib/api";
import { fetchCurrentUser, isAdmin } from "@/lib/session";
import { useToast } from "@/components/ui/use-toast";

interface PublicKnowledgeBase {
  id: number;
  name: string;
  description: string;
  documents: Array<{
    id: number;
    file_name: string;
    content_type: string;
    created_at: string;
  }>;
}

export default function KnowledgeBaseDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const { toast } = useToast();
  const [user, setUser] = useState<AuthenticatedUser | null | undefined>(
    undefined,
  );
  const [knowledgeBase, setKnowledgeBase] = useState<PublicKnowledgeBase | null>(
    null,
  );
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    const load = async () => {
      const currentUser = await fetchCurrentUser();
      setUser(currentUser);
      if (isAdmin(currentUser)) {
        return;
      }

      try {
        const kb = (await api.get("/api/public/knowledge-base")) as PublicKnowledgeBase;
        if (String(kb.id) !== params.id) {
          setMissing(true);
          return;
        }
        setKnowledgeBase(kb);
      } catch (error) {
        setMissing(true);
        if (error instanceof ApiError) {
          toast({
            title: "Error",
            description: error.message,
            variant: "destructive",
          });
        }
      }
    };

    void load();
  }, [params.id, toast]);

  if (missing) {
    return (
      <DashboardLayout>
        <div className="mx-auto max-w-3xl rounded-2xl border bg-card p-8 text-sm text-muted-foreground shadow-sm">
          This knowledge base is not available.
        </div>
      </DashboardLayout>
    );
  }

  if (isAdmin(user ?? null)) {
    return <AdminKnowledgeBasePage />;
  }

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="rounded-2xl border bg-card p-6 shadow-sm">
          <h1 className="text-3xl font-bold tracking-tight">
            {knowledgeBase?.name || "Knowledge Base"}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {knowledgeBase?.description || "Public knowledge base"}
          </p>
        </div>

        <div className="rounded-2xl border bg-card p-6 shadow-sm">
          <h2 className="text-lg font-semibold">Documents</h2>
          {knowledgeBase?.documents.length ? (
            <div className="mt-4 space-y-3">
              {knowledgeBase.documents.map((document) => (
                <div
                  key={document.id}
                  className="rounded-xl border px-4 py-3"
                >
                  <div className="font-medium">{document.file_name}</div>
                  <div className="mt-1 text-sm text-muted-foreground">
                    {document.content_type} ·{" "}
                    {new Date(document.created_at).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-4 text-sm text-muted-foreground">
              No documents are available.
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
