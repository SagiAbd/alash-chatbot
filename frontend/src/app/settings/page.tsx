"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import AdminSettingsPage from "@/app/admin/settings/page";
import DashboardLayout from "@/components/layout/dashboard-layout";
import { fetchCurrentUser, isAdmin } from "@/lib/session";
import { AuthenticatedUser } from "@/lib/auth";

export default function SettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthenticatedUser | null | undefined>(
    undefined,
  );

  useEffect(() => {
    const load = async () => {
      const currentUser = await fetchCurrentUser();
      if (!isAdmin(currentUser)) {
        router.replace("/");
        return;
      }
      setUser(currentUser);
    };

    void load();
  }, [router]);

  if (user === undefined) {
    return (
      <DashboardLayout>
        <div className="flex min-h-[70vh] items-center justify-center text-sm text-muted-foreground">
          Loading settings...
        </div>
      </DashboardLayout>
    );
  }

  return <AdminSettingsPage />;
}
