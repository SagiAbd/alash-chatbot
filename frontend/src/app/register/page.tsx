"use client";

import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
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

export default function RegisterPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = sanitizeNextPath(searchParams.get("next"), "/");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const loginUrl = useMemo(() => {
    const params = new URLSearchParams({ next: nextPath });
    return `/login?${params.toString()}`;
  }, [nextPath]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setLoading(true);

    const formData = new FormData(event.currentTarget);
    const username = String(formData.get("username") ?? "").trim();
    const email = String(formData.get("email") ?? "").trim();
    const password = String(formData.get("password") ?? "");
    const confirmPassword = String(formData.get("confirmPassword") ?? "");

    if (password !== confirmPassword) {
      setError("Құпиясөздер бірдей емес");
      setLoading(false);
      return;
    }

    try {
      await api.post("/api/auth/register", {
        username,
        email,
        password,
      });

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
    } catch (err) {
      localStorage.removeItem("token");
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Тіркелу сәтсіз аяқталды");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-md">
        <div className="space-y-6 rounded-lg bg-white p-8 shadow-md">
          <div className="text-center">
            <h1 className="text-3xl font-bold text-gray-900">Тіркелу</h1>
          </div>

          <form className="space-y-6" onSubmit={handleSubmit}>
            <div className="space-y-4">
              <div>
                <label
                  htmlFor="username"
                  className="block text-sm font-medium text-gray-700"
                >
                  Пайдаланушы аты
                </label>
                <input
                  id="username"
                  name="username"
                  type="text"
                  required
                  disabled={loading}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                  placeholder="Пайдаланушы атын таңдаңыз"
                />
              </div>

              <div>
                <label
                  htmlFor="email"
                  className="block text-sm font-medium text-gray-700"
                >
                  Email
                </label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  required
                  disabled={loading}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                  placeholder="Email енгізіңіз"
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
                  placeholder="Құпиясөз енгізіңіз"
                />
              </div>

              <div>
                <label
                  htmlFor="confirmPassword"
                  className="block text-sm font-medium text-gray-700"
                >
                  Құпиясөзді қайталаңыз
                </label>
                <input
                  id="confirmPassword"
                  name="confirmPassword"
                  type="password"
                  required
                  disabled={loading}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                  placeholder="Құпиясөзді қайта енгізіңіз"
                />
              </div>
            </div>

            {error && (
              <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center rounded-md bg-gray-700 px-4 py-3 text-sm font-medium text-white shadow-sm transition-colors hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Тіркеліп жатыр..." : "Тіркелу"}
            </button>
          </form>

          <div className="text-center text-sm text-gray-600">
            Аккаунтыңыз бар ма?{" "}
            <Link
              href={loginUrl}
              className="font-medium text-gray-900 hover:text-gray-700"
            >
              Жүйеге кіру
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}
