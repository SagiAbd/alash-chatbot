"use client";

import { useEffect, useState } from "react";
import DashboardLayout from "@/components/layout/dashboard-layout";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/use-toast";

interface KnowledgeBase {
  id: number;
  name: string;
}

interface AppSettings {
  public_kb_id: number | null;
  chat_provider: string;
  chat_model: string | null;
  welcome_title: string;
  welcome_text: string;
}

const DEFAULT_SETTINGS: AppSettings = {
  public_kb_id: null,
  chat_provider: "openai",
  chat_model: "",
  welcome_title: "",
  welcome_text: "",
};

export default function AdminSettingsPage() {
  const { toast } = useToast();
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const [settingsData, kbData] = await Promise.all([
          api.get("/api/settings"),
          api.get("/api/knowledge-base"),
        ]);
        setSettings({
          ...(settingsData as AppSettings),
          chat_model: (settingsData as AppSettings).chat_model || "",
        });
        setKnowledgeBases(kbData as KnowledgeBase[]);
      } catch (error) {
        if (error instanceof ApiError) {
          toast({
            title: "Error",
            description: error.message,
            variant: "destructive",
          });
        }
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, [toast]);

  const handleSave = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSaving(true);
    try {
      const data = (await api.put("/api/settings", {
        ...settings,
        chat_model: settings.chat_model || null,
      })) as AppSettings;
      setSettings({
        ...data,
        chat_model: data.chat_model || "",
      });
      toast({
        title: "Saved",
        description: "Settings updated successfully",
      });
    } catch (error) {
      if (error instanceof ApiError) {
        toast({
          title: "Error",
          description: error.message,
          variant: "destructive",
        });
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="max-w-3xl mx-auto space-y-8">
        <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <h2 className="text-3xl font-bold tracking-tight text-slate-900">
            Settings
          </h2>
          <p className="mt-2 text-slate-500">
            Configure the public chatbot knowledge base, model, and welcome
            content.
          </p>
        </div>

        {loading ? (
          <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm text-slate-500">
            Loading settings...
          </div>
        ) : (
          <form
            onSubmit={handleSave}
            className="space-y-6 rounded-2xl border border-slate-200 bg-white p-8 shadow-sm"
          >
            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-700">
                Public chatbot knowledge base
              </label>
              <select
                value={settings.public_kb_id ?? ""}
                onChange={(e) =>
                  setSettings((prev) => ({
                    ...prev,
                    public_kb_id: e.target.value ? Number(e.target.value) : null,
                  }))
                }
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="">Not configured</option>
                {knowledgeBases.map((kb) => (
                  <option key={kb.id} value={kb.id}>
                    {kb.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-slate-700">
                  Chat provider
                </label>
                <select
                  value={settings.chat_provider}
                  onChange={(e) =>
                    setSettings((prev) => ({
                      ...prev,
                      chat_provider: e.target.value,
                    }))
                  }
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="openai">OpenAI</option>
                  <option value="deepseek">DeepSeek</option>
                  <option value="openrouter">OpenRouter</option>
                </select>
              </div>

              <div className="space-y-2">
                <label className="block text-sm font-medium text-slate-700">
                  Chat model
                </label>
                <input
                  value={settings.chat_model ?? ""}
                  onChange={(e) =>
                    setSettings((prev) => ({
                      ...prev,
                      chat_model: e.target.value,
                    }))
                  }
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Model name"
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-700">
                Welcome title
              </label>
              <input
                value={settings.welcome_title}
                onChange={(e) =>
                  setSettings((prev) => ({
                    ...prev,
                    welcome_title: e.target.value,
                  }))
                }
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-medium text-slate-700">
                Welcome text
              </label>
              <textarea
                value={settings.welcome_text}
                onChange={(e) =>
                  setSettings((prev) => ({
                    ...prev,
                    welcome_text: e.target.value,
                  }))
                }
                className="mt-1 block min-h-[140px] w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={saving}
                className="inline-flex items-center justify-center rounded-full bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors duration-200 shadow-sm disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saving ? "Saving..." : "Save settings"}
              </button>
            </div>
          </form>
        )}
      </div>
    </DashboardLayout>
  );
}
