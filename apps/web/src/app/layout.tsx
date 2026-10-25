import type { Metadata, Viewport } from "next";

import { Analytics } from "@/components/Analytics";
import { AppShell } from "@/components/AppShell";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "MAIROS — Multi-Agent Research Assistant",
    template: "%s — MAIROS",
  },
  description:
    "Multi-Agent Intelligent Research & Orchestration System. Ask complex research questions and receive citation-backed answers.",
};

export const viewport: Viewport = {
  themeColor: "#080813",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background text-foreground antialiased">
        <AppShell>{children}</AppShell>
        <Analytics />
      </body>
    </html>
  );
}
