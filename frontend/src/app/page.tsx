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
        <div className="mb-12 flex justify-end">
          <Link
            href="/admin/login"
            className="px-5 py-2.5 bg-gray-200 text-gray-800 rounded-full text-sm font-medium transition-all duration-300 hover:bg-gray-300"
          >
            Жүйеге кіру
          </Link>
        </div>

        <div className="text-center space-y-8 mb-24">
          <h1 className="text-5xl sm:text-7xl font-bold tracking-tight text-black">
            {config.welcome_title}
          </h1>
          <p className="text-xl sm:text-2xl text-gray-500 max-w-3xl mx-auto font-light leading-relaxed">
            {config.welcome_text}
          </p>
          <div className="mt-12 flex justify-center">
            <Link
              href="/chat"
              className="px-8 py-4 bg-blue-600 text-white rounded-full text-lg font-medium transition-all duration-300 hover:bg-blue-700 w-full sm:w-auto"
            >
              Чатқа өту
            </Link>
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
