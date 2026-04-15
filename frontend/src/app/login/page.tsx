"use client";

import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import {
  AuthenticatedUser,
  getPostAuthDestination,
  sanitizeNextPath,
} from "@/lib/auth";

interface LoginResponse {
  access_token: string;
  token_type: string;
}

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = sanitizeNextPath(searchParams.get("next"), "/");
  const [submitError, setSubmitError] = useState("");
  const [loading, setLoading] = useState(false);

  const registerUrl = useMemo(() => {
    const params = new URLSearchParams({ next: nextPath });
    return `/register?${params.toString()}`;
  }, [nextPath]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitError("");
    setLoading(true);

    const formData = new FormData(event.currentTarget);
    const username = String(formData.get("username") ?? "").trim();
    const password = String(formData.get("password") ?? "");

    try {
      const encodedBody = new URLSearchParams();
      encodedBody.append("username", username);
      encodedBody.append("password", password);

      const tokenData = (await api.post("/api/auth/token", encodedBody, {
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
      })) as LoginResponse;

      localStorage.setItem("token", tokenData.access_token);
      const currentUser = (await api.get("/api/auth/me")) as AuthenticatedUser;
      router.replace(getPostAuthDestination(currentUser, nextPath));
    } catch (error) {
      localStorage.removeItem("token");
      if (error instanceof ApiError) {
        setSubmitError(error.message);
      } else {
        setSubmitError("Кіру сәтсіз аяқталды");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-md">
        <div className="space-y-6 rounded-lg bg-white p-8 shadow-md">
          <div className="text-center">
            <h1 className="text-3xl font-bold text-gray-900">Жүйеге кіру</h1>
            <p className="mt-2 text-sm text-gray-600">
              Кіргеннен кейін чат тарихы мен жеке кітапхана қолжетімді болады.
            </p>
          </div>

          <form className="space-y-6" onSubmit={handleSubmit}>
            <div className="space-y-4">
              <div>
                <label
                  htmlFor="username"
                  className="block text-sm font-medium text-gray-700"
                >
                  Пайдаланушы аты немесе email
                </label>
                <input
                  id="username"
                  name="username"
                  type="text"
                  required
                  disabled={loading}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                  placeholder="Пайдаланушы аты немесе email енгізіңіз"
                />
              </div>

              <div>
                <label
                  htmlFor="password"
                  className="block text-sm font-medium text-gray-700"
                >
                  Құпиясөз
                </label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  required
                  disabled={loading}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                  placeholder="Құпиясөзді енгізіңіз"
                />
              </div>
            </div>

            {submitError && (
              <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
                {submitError}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center rounded-md bg-gray-700 px-4 py-3 text-sm font-medium text-white shadow-sm transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Кіріп жатыр..." : "Кіру"}
            </button>
          </form>

          <div className="text-center text-sm text-gray-600">
            Аккаунтыңыз жоқ па?{" "}
            <Link
              href={registerUrl}
              className="font-medium text-gray-900 hover:text-gray-700"
            >
              Тіркелу
            </Link>
          </div>

          <div className="text-center">
            <Link href="/" className="text-sm font-medium text-gray-600 hover:text-gray-500">
              Чатқа оралу
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}
