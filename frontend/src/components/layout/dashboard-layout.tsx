"use client";

import { useState, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { Book, MessageSquare, LogOut, Menu, SlidersHorizontal } from "lucide-react";
import Breadcrumb from "@/components/ui/breadcrumb";
import { api } from "@/lib/api";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isCheckingSession, setIsCheckingSession] = useState(true);

  useEffect(() => {
    const checkSession = async () => {
      const token = localStorage.getItem("token");
      if (!token) {
        router.push("/admin/login");
        return;
      }

      try {
        await api.post("/api/auth/test-token");
        setIsCheckingSession(false);
      } catch {
        localStorage.removeItem("token");
        router.push("/admin/login");
      }
    };

    void checkSession();
  }, [router]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    router.push("/admin/login");
  };

  const navigation = [
    { name: "Knowledge Base", href: "/admin/knowledge", icon: Book },
    { name: "Chat", href: "/admin/chat", icon: MessageSquare },
    { name: "Settings", href: "/admin/settings", icon: SlidersHorizontal },
  ];

  if (isCheckingSession) {
    return <div className="min-h-screen bg-background" />;
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Mobile menu button */}
      <div className="lg:hidden fixed top-0 left-0 m-4 z-50">
        <button
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          className="p-2 rounded-md bg-primary text-primary-foreground"
        >
          <Menu className="h-6 w-6" />
        </button>
      </div>

      {/* Sidebar */}
      <div
        className={`fixed inset-y-0 left-0 z-40 w-64 transform bg-card border-r transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          isMobileMenuOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-full flex-col">
          {/* Sidebar header */}
          <div className="flex h-16 items-center border-b pl-8">
            <Link
              href="/admin"
              className="flex items-center text-lg font-semibold hover:text-primary transition-colors"
            >
              <img
                src="/logo.svg"
                alt="Logo"
                className="w-16 h-16 rounded-lg"
              />
              Alash Chatbot
            </Link>
          </div>

          {/* Navigation */}
          <nav className="flex-1 space-y-2 px-4 py-6">
            {navigation.map((item) => {
              const isActive = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={`group flex items-center rounded-lg px-4 py-3 text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? "bg-gradient-to-r from-primary/10 to-primary/5 text-primary shadow-sm"
                      : "text-muted-foreground hover:bg-accent/50 hover:text-foreground hover:shadow-sm"
                  }`}
                >
                  <item.icon
                    className={`mr-3 h-5 w-5 transition-transform duration-200 ${
                      isActive
                        ? "text-primary scale-110"
                        : "group-hover:scale-110"
                    }`}
                  />
                  <span className="font-medium">{item.name}</span>
                  {isActive && (
                    <div className="ml-auto h-1.5 w-1.5 rounded-full bg-primary" />
                  )}
                </Link>
              );
            })}
          </nav>
          {/* User profile and logout */}
          <div className="border-t p-4 space-y-4">
            <button
              onClick={handleLogout}
              className="flex w-full items-center rounded-lg px-3 py-2.5 text-sm font-medium text-destructive hover:bg-destructive/10 transition-colors duration-200"
            >
              <LogOut className="mr-3 h-4 w-4" />
              Sign out
            </button>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="lg:pl-64">
        <main className="min-h-screen py-6 px-4 sm:px-6 lg:px-8">
          <Breadcrumb />
          {children}
        </main>
      </div>
    </div>
  );
}

export const dashboardConfig = {
  mainNav: [],
  sidebarNav: [
    {
      title: "Knowledge Base",
      href: "/admin/knowledge",
      icon: "database",
    },
    {
      title: "Chat",
      href: "/admin/chat",
      icon: "messageSquare",
    },
    {
      title: "Settings",
      href: "/admin/settings",
      icon: "slidersHorizontal",
    },
  ],
};
