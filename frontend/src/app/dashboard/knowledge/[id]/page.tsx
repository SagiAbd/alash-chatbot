"use client";

import { useParams } from "next/navigation";
import { useState, useCallback } from "react";
import { DocumentList } from "@/components/knowledge-base/document-list";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import { Download, Upload, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useDropzone } from "react-dropzone";
import DashboardLayout from "@/components/layout/dashboard-layout";

interface QueuedFile {
  file: File;
  status: "uploading" | "done" | "error";
  error?: string;
}

export default function KnowledgeBasePage() {
  const params = useParams();
  const knowledgeBaseId = parseInt(params.id as string);
  const { toast } = useToast();
  const [queuedFiles, setQueuedFiles] = useState<QueuedFile[]>([]);
  const [listRefreshKey, setListRefreshKey] = useState(0);
  const [exporting, setExporting] = useState(false);

  const uploadAndProcess = useCallback(
    async (files: File[]) => {
      const newEntries: QueuedFile[] = files.map((f) => ({
        file: f,
        status: "uploading",
      }));
      setQueuedFiles((prev) => [...prev, ...newEntries]);

      const formData = new FormData();
      files.forEach((f) => formData.append("files", f));

      try {
        const uploadResults = await api.post(
          `/api/knowledge-base/${knowledgeBaseId}/documents/upload`,
          formData
        );

        const toProcess = uploadResults.filter(
          (r: { skip_processing: boolean }) => !r.skip_processing
        );

        if (toProcess.length > 0) {
          await api.post(
            `/api/knowledge-base/${knowledgeBaseId}/documents/process`,
            toProcess
          );
        }

        setQueuedFiles((prev) =>
          prev.map((entry) =>
            files.includes(entry.file) ? { ...entry, status: "done" } : entry
          )
        );
        setListRefreshKey((k) => k + 1);
        setTimeout(() => {
          setQueuedFiles((prev) => prev.filter((entry) => !files.includes(entry.file)));
        }, 2000);
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Upload failed";
        setQueuedFiles((prev) =>
          prev.map((entry) =>
            files.includes(entry.file)
              ? { ...entry, status: "error", error: message }
              : entry
          )
        );
        toast({ title: "Upload failed", description: message, variant: "destructive" });
      }
    },
    [knowledgeBaseId, toast]
  );

  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted.length > 0) uploadAndProcess(accepted);
    },
    [uploadAndProcess]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/json": [".json"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
    },
    multiple: true,
  });

  const removeQueued = (index: number) =>
    setQueuedFiles((prev) => prev.filter((_, i) => i !== index));

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      const token =
        typeof window !== "undefined" ? localStorage.getItem("token") || "" : "";
      const response = await fetch(`/api/knowledge-base/${knowledgeBaseId}/export`, {
        method: "GET",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new ApiError(
          response.status,
          errorData.message || errorData.detail || "Failed to export knowledge base"
        );
      }

      const blob = await response.blob();
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      const contentDisposition = response.headers.get("content-disposition") || "";
      const fileNameMatch = contentDisposition.match(/filename=\"([^\"]+)\"/i);

      link.href = objectUrl;
      link.download = fileNameMatch?.[1] || `knowledge-base-${knowledgeBaseId}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(objectUrl);

      toast({
        title: "Success",
        description: "Knowledge base exported successfully",
      });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Export failed";
      toast({
        title: "Export failed",
        description: message,
        variant: "destructive",
      });
    } finally {
      setExporting(false);
    }
  }, [knowledgeBaseId, toast]);

  return (
    <DashboardLayout>
      <div className="mb-8">
        <h1 className="text-3xl font-bold">Knowledge Base</h1>
      </div>

      {/* Primary actions */}
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div {...getRootProps()}>
          <input {...getInputProps()} />
          <Button variant="outline" className="gap-2">
            <Upload className="h-4 w-4" />
            Upload documents
          </Button>
        </div>
        <Button
          variant="outline"
          className="gap-2"
          onClick={handleExport}
          disabled={exporting}
        >
          <Download className="h-4 w-4" />
          {exporting ? "Exporting..." : "Export KB"}
        </Button>
      </div>

      {/* Upload queue — transient per-session feedback */}
      {queuedFiles.length > 0 && (
        <div className="mb-6 space-y-2">
          {queuedFiles.map((entry, i) => (
            <div
              key={i}
              className="flex items-center justify-between rounded-md border px-4 py-2 text-sm"
            >
              <span className="truncate max-w-[60%]">{entry.file.name}</span>
              <div className="flex items-center gap-3">
                {entry.status === "uploading" && (
                  <span className="text-muted-foreground animate-pulse">Uploading…</span>
                )}
                {entry.status === "done" && (
                  <span className="text-green-600">Queued for processing</span>
                )}
                {entry.status === "error" && (
                  <span className="text-destructive">{entry.error}</span>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeQueued(i);
                  }}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <DocumentList key={listRefreshKey} knowledgeBaseId={knowledgeBaseId} />
    </DashboardLayout>
  );
}
