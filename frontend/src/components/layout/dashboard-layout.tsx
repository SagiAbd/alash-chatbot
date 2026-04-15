"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Book,
  Library,
  LogIn,
  LogOut,
  Menu,
  MessageSquare,
  Plus,
  Settings,
} from "lucide-react";
import Breadcrumb from "@/components/ui/breadcrumb";
import { AuthenticatedUser } from "@/lib/auth";
import { fetchCurrentUser, isAdmin } from "@/lib/session";
import { api } from "@/lib/api";

interface SidebarChat {
  id: number;
  title: string;
  updated_at: string;
}

function isRouteActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/" || pathname.startsWith("/chat");
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [recentChats, setRecentChats] = useState<SidebarChat[]>([]);

  useEffect(() => {
    const loadSession = async () => {
      const currentUser = await fetchCurrentUser();
      setUser(currentUser);
      setIsCheckingSession(false);
    };

    void loadSession();
  }, [pathname]);

  useEffect(() => {
    const loadChats = async () => {
      if (!user) {
        setRecentChats([]);
        return;
      }

      try {
        const data = (await api.get("/api/chat")) as SidebarChat[];
        setRecentChats(data);
      } catch {
        setRecentChats([]);
      }
    };

    void loadChats();
  }, [user, pathname]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    setUser(null);
    setRecentChats([]);
    router.push("/");
  };

  const navigation = useMemo(() => {
    const items = [
      { name: "Chat", href: "/", icon: MessageSquare },
      { name: "Knowledge Base", href: "/knowledge", icon: Book },
    ];

    if (user) {
      items.push({ name: "My Library", href: "/library", icon: Library });
    }

    if (isAdmin(user)) {
      items.push({ name: "Settings", href: "/settings", icon: Settings });
    }

    return items;
  }, [user]);

  if (isCheckingSession) {
    return <div className="min-h-screen bg-background" />;
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="fixed left-0 top-0 z-50 m-4 lg:hidden">
        <button
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          className="rounded-md bg-primary p-2 text-primary-foreground"
        >
          <Menu className="h-6 w-6" />
        </button>
      </div>

      <div
        className={`fixed inset-y-0 left-0 z-40 w-72 transform border-r bg-card transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          isMobileMenuOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-full flex-col">
          <div className="flex h-20 items-center border-b px-6">
            <Link href="/" className="group flex items-center gap-3 transition-colors">
              <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-sm font-semibold text-primary-foreground shadow-sm">
                A
              </span>
              <span className="flex flex-col">
                <span className="text-sm font-semibold text-foreground group-hover:text-primary">
                  Alash Chatbot
                </span>
                <span className="text-xs uppercase tracking-[0.24em] text-muted-foreground">
                  {isAdmin(user)
                    ? "Admin Workspace"
                    : user
                    ? "Personal Workspace"
                    : "Guest Workspace"}
                </span>
              </span>
            </Link>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-6">
            <div className="space-y-2">
              <Link
                href="/chat/new"
                className="flex items-center justify-center rounded-lg bg-primary px-4 py-3 text-sm font-medium text-primary-foreground transition-all duration-200 hover:bg-primary/90"
              >
                <Plus className="mr-2 h-4 w-4" />
                New chat
              </Link>

              {navigation.map((item) => {
                const isActive = isRouteActive(pathname, item.href);
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
                        isActive ? "scale-110 text-primary" : "group-hover:scale-110"
                      }`}
                    />
                    <span>{item.name}</span>
                  </Link>
                );
              })}
            </div>

            {user && (
              <div className="mt-8">
                <div className="mb-3 px-2 text-xs font-semibold uppercase tracking-[0.24em] text-muted-foreground">
                  Recent chats
                </div>
                <div className="space-y-1">
                  {recentChats.length === 0 ? (
                    <div className="rounded-lg px-3 py-2 text-sm text-muted-foreground">
                      No saved chats yet.
                    </div>
                  ) : (
                    recentChats.map((chat) => (
                      <Link
                        key={chat.id}
                        href={`/chat/${chat.id}`}
                        className={`block rounded-lg px-3 py-2 text-sm transition-colors ${
                          pathname === `/chat/${chat.id}`
                            ? "bg-accent text-foreground"
                            : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
                        }`}
                      >
                        <div className="truncate font-medium">
                          {chat.title || "Untitled chat"}
                        </div>
                        <div className="truncate text-xs text-muted-foreground">
                          {new Date(chat.updated_at).toLocaleString()}
                        </div>
                      </Link>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="space-y-3 border-t p-4">
            {user ? (
              <>
                <div className="rounded-lg bg-muted/50 px-3 py-2">
                  <div className="text-sm font-medium text-foreground">
                    {user.username}
                  </div>
                  <div className="text-xs text-muted-foreground">{user.email}</div>
                </div>
                <button
                  onClick={handleLogout}
                  className="flex w-full items-center rounded-lg px-3 py-2.5 text-sm font-medium text-destructive transition-colors duration-200 hover:bg-destructive/10"
                >
                  <LogOut className="mr-3 h-4 w-4" />
                  Sign out
                </button>
              </>
            ) : (
              <Link
                href={`/login?next=${encodeURIComponent(pathname)}`}
                className="flex items-center rounded-lg px-3 py-2.5 text-sm font-medium text-foreground transition-colors duration-200 hover:bg-accent/50"
              >
                <LogIn className="mr-3 h-4 w-4" />
                Sign in
              </Link>
            )}
          </div>
        </div>
      </div>

      <div className="lg:pl-72">
        <main className="min-h-screen px-4 py-6 sm:px-6 lg:px-8">
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
      title: "Chat",
      href: "/",
      icon: "messageSquare",
    },
    {
      title: "Knowledge Base",
      href: "/knowledge",
      icon: "database",
    },
    {
      title: "My Library",
      href: "/library",
      icon: "library",
    },
    {
      title: "Settings",
      href: "/settings",
      icon: "slidersHorizontal",
    },
  ],
};
