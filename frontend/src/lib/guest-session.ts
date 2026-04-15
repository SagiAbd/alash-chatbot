"use client";

const GUEST_TOKEN_STORAGE_KEY = "guest_chat_token";

function buildGuestToken(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID().replace(/-/g, "");
  }

  return `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
}

export function getGuestSessionToken(): string {
  if (typeof window === "undefined") {
    return "";
  }

  const existing = window.localStorage.getItem(GUEST_TOKEN_STORAGE_KEY);
  if (existing) {
    return existing;
  }

  const token = buildGuestToken();
  window.localStorage.setItem(GUEST_TOKEN_STORAGE_KEY, token);
  return token;
}
