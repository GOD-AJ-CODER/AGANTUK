import type { Metadata } from "next";
import "./globals.css";
import Header from "../components/Header";

export const metadata: Metadata = {
  title: "AGANTUK (आगंतुक) — Border Security Operations Portal",
  description: "Arrival & Guest Administration, Navigation, Tracking, Utility & Knowledge Engine.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="bg-[#F4F6F8] text-[#0F172A] min-h-screen flex flex-col font-sans antialiased">
        {/* Navy Header with Brand & Navigation */}
        <Header />

        {/* Main Clean Workspace */}
        <main className="flex-1 w-full max-w-7xl mx-auto p-4 md:p-6 flex flex-col">
          {children}
        </main>

        {/* Operational Footer */}
        <footer className="w-full bg-white border-t border-[#E2E8F0] px-4 py-3 text-xs text-[#64748B]">
          <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-2">
            <div>
              <span className="font-bold text-[#0F172A]">AGANTUK (आगंतुक)</span> — IMMIGRATION & BORDER TRANSIT DESK
            </div>
            <div className="flex items-center gap-4 font-mono text-[11px]">
              <span>SQLITE WAL ACTIVE</span>
              <span>•</span>
              <span>SHA-256 NON-REPUDIATION</span>
              <span>•</span>
              <span className="text-[#059669] font-bold">100% LOCAL EDGE SECURE</span>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
