import { getGuestSessionToken } from "@/lib/guest-session";

export function buildChatHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};

  if (typeof window === "undefined") {
    return headers;
  }

  const token = window.localStorage.getItem("token");
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  headers["X-Guest-Token"] = getGuestSessionToken();
  return headers;
}
