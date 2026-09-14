"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Shield, Scan, FileText, Settings, Radio } from "lucide-react";
import SettingsModal from "./SettingsModal";

export default function Header() {
  const pathname = usePathname();
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  const isScanActive = pathname === "/scan" || pathname === "/";
  const isLogsActive = pathname === "/logs";

  return (
    <>
      <header className="w-full bg-[#0F172A] text-white border-b border-[#1E293B] shadow-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 md:px-6 py-2.5 flex flex-wrap items-center justify-between gap-4">
          {/* Brand Logo & Title */}
          <Link href="/scan" className="flex items-center gap-3 group">
            <div className="w-9 h-9 rounded bg-gradient-to-tr from-[#0EA5E9] to-[#38BDF8] flex items-center justify-center text-[#0F172A] font-black shadow-sm group-hover:scale-105 transition-transform">
              <Shield className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-black text-lg tracking-wider text-white">AGANTUK</span>
                <span className="text-xs px-1.5 py-0.5 rounded bg-[#1E293B] text-[#38BDF8] font-bold">
                  आगंतुक
                </span>
              </div>
              <div className="text-[11px] text-[#94A3B8] font-medium hidden sm:block">
                Arrival & Guest Administration, Navigation, Tracking, Utility & Knowledge Engine
              </div>
            </div>
          </Link>

          {/* Navigation Tabs (Connected via Next.js App Router Links) */}
          <nav className="flex items-center gap-1.5 bg-[#1E293B] p-1 rounded-md border border-[#334155]">
            <Link
              href="/scan"
              className={`flex items-center gap-2 px-4 py-2 rounded text-xs font-bold uppercase tracking-wider transition-all cursor-pointer ${
                isScanActive
                  ? "bg-[#0EA5E9] text-white shadow-sm"
                  : "text-[#94A3B8] hover:text-white hover:bg-[#334155]"
              }`}
            >
              <Scan className="w-4 h-4" />
              <span>Scanner</span>
            </Link>

            <Link
              href="/logs"
              className={`flex items-center gap-2 px-4 py-2 rounded text-xs font-bold uppercase tracking-wider transition-all cursor-pointer ${
                isLogsActive
                  ? "bg-[#0EA5E9] text-white shadow-sm"
                  : "text-[#94A3B8] hover:text-white hover:bg-[#334155]"
              }`}
            >
              <FileText className="w-4 h-4" />
              <span>Audit Logs</span>
            </Link>
          </nav>

          {/* Right Action Icons & Status */}
          <div className="flex items-center gap-3">
            <div className="hidden md:flex items-center gap-2 px-2.5 py-1.5 rounded bg-[#1E293B] border border-[#334155] text-xs font-mono text-[#10B981]">
              <Radio className="w-3.5 h-3.5 animate-pulse" />
              <span>100% OFFLINE EDGE</span>
            </div>

            <button
              onClick={() => setIsSettingsOpen(true)}
              className="flex items-center gap-2 px-3 py-2 rounded bg-[#1E293B] hover:bg-[#334155] border border-[#334155] text-white text-xs font-bold cursor-pointer transition-colors"
              title="Open System Settings"
            >
              <Settings className="w-4 h-4 text-[#38BDF8]" />
              <span className="hidden sm:inline">Settings</span>
            </button>
          </div>
        </div>
      </header>

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </>
  );
}
