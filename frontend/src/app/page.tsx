"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/dashboard-layout";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/chat/new");
  }, [router]);

  return (
    <DashboardLayout>
      <div className="flex min-h-[70vh] items-center justify-center text-sm text-muted-foreground">
        Preparing your chat...
      </div>
    </DashboardLayout>
  );
}
