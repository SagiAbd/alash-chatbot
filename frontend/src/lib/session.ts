"use client";

import { api } from "@/lib/api";
import { AuthenticatedUser } from "@/lib/auth";

export async function fetchCurrentUser(): Promise<AuthenticatedUser | null> {
  if (typeof window === "undefined") {
    return null;
  }

  const token = window.localStorage.getItem("token");
  if (!token) {
    return null;
  }

  try {
    return (await api.get("/api/auth/me")) as AuthenticatedUser;
  } catch {
    window.localStorage.removeItem("token");
    return null;
  }
}

export function isAdmin(user: AuthenticatedUser | null): boolean {
  return Boolean(user?.is_superuser);
}
