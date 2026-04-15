"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface PublicConfig {
  welcome_title: string;
  welcome_text: string;
  chat_available: boolean;
}

const DEFAULT_CONFIG: PublicConfig = {
  welcome_title: "Алаш мұрасымен сұхбат",
  welcome_text:
    "Алаш қайраткерлері, кітаптар мен ұғымдар туралы сұрақ қойыңыз. Ашық чат таңдалған білім қорына сүйеніп жауап береді.",
  chat_available: false,
};

export default function Home() {
  const [config, setConfig] = useState<PublicConfig>(DEFAULT_CONFIG);

  useEffect(() => {
    const loadConfig = async () => {
      try {
        const data = (await api.get("/api/public/config")) as PublicConfig;
        setConfig(data);
      } catch {
        setConfig(DEFAULT_CONFIG);
      }
    };

    void loadConfig();
  }, []);

  return (
    <main className="min-h-screen bg-white text-black">
      <div className="max-w-7xl mx-auto px-4 py-16 sm:py-24">
        <div className="flex items-center justify-between mb-12">
          <Link href="/" className="inline-flex items-center gap-3">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-600 text-base font-semibold text-white shadow-sm">
              A
            </span>
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-600">
                Alash Chatbot
              </p>
              <p className="mt-1 text-sm text-gray-500">
                Ашық чат тәжірибесі
              </p>
            </div>
          </Link>
          <Link
            href="/admin/login"
            className="px-5 py-2.5 bg-gray-200 text-gray-800 rounded-full text-sm font-medium transition-all duration-300 hover:bg-gray-300"
          >
            Login
          </Link>
        </div>

        <div className="text-center space-y-8 mb-24">
          <h1 className="text-5xl sm:text-7xl font-bold tracking-tight text-black">
            {config.welcome_title}
          </h1>
          <p className="text-xl sm:text-2xl text-gray-500 max-w-3xl mx-auto font-light leading-relaxed">
            {config.welcome_text}
          </p>
          <div className="flex flex-col sm:flex-row gap-6 justify-center items-center mt-12">
            <Link
              href="/chat"
              className="px-8 py-4 bg-blue-600 text-white rounded-full text-lg font-medium transition-all duration-300 hover:bg-blue-700 w-full sm:w-auto"
            >
              Чатқа өту
            </Link>
            <div className="px-8 py-4 bg-gray-100 text-gray-700 rounded-full text-sm font-medium w-full sm:w-auto">
              {config.chat_available
                ? "Қоғамдық чат белсенді"
                : "Чат әлі бапталмаған"}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-12 mb-24">
          <div className="text-center">
            <div className="h-20 w-20 mx-auto rounded-full bg-blue-100 flex items-center justify-center mb-6">
              <svg
                className="h-10 w-10 text-blue-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
            </div>
            <h3 className="text-2xl font-semibold text-black mb-4">
              Ашық чат
            </h3>
            <p className="text-gray-500 leading-relaxed">
              Сайтқа кірген кез келген адам қоғамдық чатпен сөйлесе алады.
            </p>
          </div>

          <div className="text-center">
            <div className="h-20 w-20 mx-auto rounded-full bg-blue-100 flex items-center justify-center mb-6">
              <svg
                className="h-10 w-10 text-blue-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"
                />
              </svg>
            </div>
            <h3 className="text-2xl font-semibold text-black mb-4">
              Әкімші басқарады
            </h3>
            <p className="text-gray-500 leading-relaxed">
              Білім қорын таңдау, құжаттарды жүктеу және модель баптаулары тек
              басқару панелінде реттеледі.
            </p>
          </div>

          <div className="text-center">
            <div className="h-20 w-20 mx-auto rounded-full bg-blue-100 flex items-center justify-center mb-6">
              <svg
                className="h-10 w-10 text-blue-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586A1 1 0 0113.293 3.293l4.414 4.414A1 1 0 0118 8.414V19a2 2 0 01-2 2z"
                />
              </svg>
            </div>
            <h3 className="text-2xl font-semibold text-black mb-4">
              Жаңа сессия
            </h3>
            <p className="text-gray-500 leading-relaxed">
              Қоғамдық чат ішкі түрде сақталады, бірақ пайдаланушыға бұрынғы
              тарих қайта ашылмайды.
            </p>
          </div>
        </div>

        <div className="text-center bg-gray-100 rounded-3xl p-16">
          <h2 className="text-4xl font-bold mb-6">Сұрақ қоюға дайынсыз ба?</h2>
          <p className="text-xl text-gray-500 mb-8 max-w-2xl mx-auto">
            Қоғамдық чат таңдалған білім қоры бойынша жауап береді.
          </p>
          <Link
            href="/chat"
            className="px-8 py-4 bg-blue-600 text-white rounded-full text-lg font-medium transition-all duration-300 hover:bg-blue-700"
          >
            Чатты ашу
          </Link>
        </div>
      </div>
    </main>
  );
}
