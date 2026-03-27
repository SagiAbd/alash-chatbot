"use client";

import { useParams } from "next/navigation";
import { useState, useCallback } from "react";
import { DocumentList } from "@/components/knowledge-base/document-list";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import { Upload, X } from "lucide-react";
import { cn } from "@/lib/utils";
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
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
      "text/plain": [".txt"],
      "text/markdown": [".md"],
      "application/json": [".json"],
    },
    multiple: true,
  });

  const removeQueued = (index: number) =>
    setQueuedFiles((prev) => prev.filter((_, i) => i !== index));

  return (
    <DashboardLayout>
      <div className="mb-8">
        <h1 className="text-3xl font-bold">Knowledge Base</h1>
      </div>

      {/* Inline drop zone */}
      <div
        {...getRootProps()}
        className={cn(
          "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors mb-6",
          isDragActive
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25 hover:border-primary/50"
        )}
      >
        <input {...getInputProps()} />
        <Upload className="w-8 h-8 mx-auto mb-3 text-muted-foreground" />
        {isDragActive ? (
          <p className="text-primary font-medium">Drop files here…</p>
        ) : (
          <>
            <p className="font-medium">Drag & drop files here, or click to select</p>
            <p className="text-sm text-muted-foreground mt-1">
              PDF, DOCX, TXT, MD, JSON
            </p>
          </>
        )}
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
