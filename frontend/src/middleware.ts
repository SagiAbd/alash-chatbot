import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

function mapLegacyPath(pathname: string): string | null {
  if (pathname === "/admin" || pathname === "/dashboard") {
    return "/";
  }
  if (pathname === "/admin/login") {
    return "/login";
  }
  if (pathname === "/admin/chat" || pathname === "/dashboard/chat") {
    return "/";
  }
  if (
    pathname === "/admin/chat/new" ||
    pathname === "/dashboard/chat/new" ||
    pathname === "/dashboard"
  ) {
    return "/chat/new";
  }
  if (pathname.startsWith("/admin/chat/")) {
    return pathname.replace("/admin/chat/", "/chat/");
  }
  if (pathname.startsWith("/dashboard/chat/")) {
    return pathname.replace("/dashboard/chat/", "/chat/");
  }
  if (pathname === "/admin/knowledge" || pathname === "/dashboard/knowledge") {
    return "/knowledge";
  }
  if (pathname.startsWith("/admin/knowledge/")) {
    return pathname.replace("/admin", "");
  }
  if (pathname.startsWith("/dashboard/knowledge/")) {
    return pathname.replace("/dashboard", "");
  }
  if (pathname === "/admin/settings") {
    return "/settings";
  }
  return null;
}

export function middleware(request: NextRequest) {
  const destination = mapLegacyPath(request.nextUrl.pathname);
  if (!destination) {
    return NextResponse.next();
  }
  return NextResponse.redirect(new URL(destination, request.url));
}

export const config = {
  matcher: ["/admin/:path*", "/dashboard/:path*"],
};
