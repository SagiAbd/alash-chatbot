"use client";

import { useEffect, useState } from "react";
import AdminKnowledgeBasePage from "@/app/dashboard/knowledge/[id]/page";
import DashboardLayout from "@/components/layout/dashboard-layout";
import { PublicDocumentViewer } from "@/components/knowledge-base/public-document-viewer";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
    analysis?: DocumentAnalysis;
  }>;
}

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

type PublicDocument = PublicKnowledgeBase["documents"][number];

function buildDisplayTitle(document: PublicDocument): string {
  const analysis = document.analysis ?? null;
  const glossaryAnalysis =
    (analysis as GlossaryAnalysis | null)?.type === "glossary"
      ? (analysis as GlossaryAnalysis)
      : null;
  const glossaryTitle = glossaryAnalysis?.title?.trim();
  const glossaryAuthor =
    glossaryAnalysis?.source_author?.trim() ||
    glossaryAnalysis?.authors?.[0]?.trim();

  if (glossaryAnalysis && glossaryTitle) {
    return glossaryAuthor
      ? `${glossaryAuthor} - ${glossaryTitle}`
      : glossaryTitle;
  }

  return document.file_name;
}

function isGlossaryDocument(document: PublicDocument): boolean {
  return (document.analysis as GlossaryAnalysis | null)?.type === "glossary";
}

function DocumentItems({ documents }: { documents: PublicDocument[] }) {
  if (documents.length === 0) {
    return (
      <div className="text-sm text-muted-foreground">
        Бұл бөлімде құжаттар жоқ.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {documents.map((document) => (
        <div
          key={document.id}
          className="flex items-center justify-between gap-4 rounded-xl border px-4 py-3"
        >
          <div className="min-w-0">
            <div className="truncate font-medium">
              {buildDisplayTitle(document)}
            </div>
          </div>
          <PublicDocumentViewer document={document} />
        </div>
      ))}
    </div>
  );
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
            title: "Қате",
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
          Бұл білім қоры қолжетімсіз.
        </div>
      </DashboardLayout>
    );
  }

  if (isAdmin(user ?? null)) {
    return <AdminKnowledgeBasePage />;
  }

  const documents = knowledgeBase?.documents ?? [];
  const books = documents.filter((document) => !isGlossaryDocument(document));
  const sheets = documents.filter((document) => isGlossaryDocument(document));

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-4xl space-y-6">
        <div className="rounded-2xl border bg-card p-6 shadow-sm">
          <h2 className="text-lg font-semibold">Кітаптар</h2>
          {documents.length ? (
            <Tabs defaultValue="books" className="mt-4 w-full">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="books">
                  Кітаптар ({books.length})
                </TabsTrigger>
                <TabsTrigger value="sheets">
                  Пәнсөздер ({sheets.length})
                </TabsTrigger>
              </TabsList>
              <TabsContent value="books" className="mt-4">
                <DocumentItems documents={books} />
              </TabsContent>
              <TabsContent value="sheets" className="mt-4">
                <DocumentItems documents={sheets} />
              </TabsContent>
            </Tabs>
          ) : (
            <div className="mt-4 text-sm text-muted-foreground">
              Кітаптар қолжетімді емес.
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
