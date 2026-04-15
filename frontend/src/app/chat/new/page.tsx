"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/dashboard-layout";
import { ApiError, api } from "@/lib/api";
import { useToast } from "@/components/ui/use-toast";

interface NewChatResponse {
  id: number;
}

export default function NewChatPage() {
  const router = useRouter();
  const { toast } = useToast();
  const startedRef = useRef(false);

  useEffect(() => {
    const bootstrap = async () => {
      if (startedRef.current) {
        return;
      }
      startedRef.current = true;

      try {
        const data = (await api.post("/api/chat")) as NewChatResponse;
        router.replace(`/chat/${data.id}`);
      } catch (error) {
        const message =
          error instanceof ApiError
            ? error.message
            : "Unable to start a new chat right now.";
        toast({
          title: "Could not start chat",
          description: message,
          variant: "destructive",
        });
      }
    };

    void bootstrap();
  }, [router, toast]);

  return (
    <DashboardLayout>
      <div className="flex min-h-[70vh] items-center justify-center text-sm text-muted-foreground">
        Starting a new chat...
      </div>
    </DashboardLayout>
  );
}
