// SANDBOX: Banking Web UI — no live banking data; backend is LangGraph sandbox.
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Banxe Banking Engine — Sandbox",
  description: "SANDBOX ONLY: Banking Engine chat interface. No live banking data.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
