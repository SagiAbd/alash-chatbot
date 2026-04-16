import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import "highlight.js/styles/github.css";
// 如果使用 App Router
import { Toaster } from "@/components/ui/toaster";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Alash Science",
  description: "Алаш ЖИ Көмекшісі және админдік басқару панелі",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="kk">
      <body className={inter.className}>
        {children}
        <Toaster />
      </body>
    </html>
  );
}
