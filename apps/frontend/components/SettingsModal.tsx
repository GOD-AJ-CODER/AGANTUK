"use client";

import React from "react";
import { X, Settings, Database, ShieldCheck, Cpu, UserCheck, HardDrive, WifiOff } from "lucide-react";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  officerId?: string;
}

export default function SettingsModal({
  isOpen,
  onClose,
  officerId = "OFF-8472",
}: SettingsModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-white border border-[#CBD5E1] rounded-lg shadow-2xl overflow-hidden flex flex-col">
        {/* Modal Header */}
        <div className="bg-[#0F172A] text-white px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded bg-[#1E293B] flex items-center justify-center text-[#38BDF8]">
              <Settings className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold tracking-wide">System Settings & Status</h2>
              <p className="text-xs text-[#94A3B8] font-mono">AGANTUK ENGINE v1.0.0 // STATION GATE-01</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 text-[#94A3B8] hover:text-white hover:bg-[#1E293B] rounded transition-colors cursor-pointer"
            aria-label="Close Settings"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-4 text-sm text-[#334155] bg-[#F8FAFC]">
          {/* Operational Parameters Grid */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-white p-3.5 rounded border border-[#E2E8F0] shadow-2xs">
              <div className="flex items-center gap-2 text-xs font-semibold text-[#64748B] uppercase tracking-wider mb-1">
                <Database className="w-4 h-4 text-[#0EA5E9]" />
                <span>Database Engine</span>
              </div>
              <div className="font-mono font-bold text-sm text-[#0F172A]">SQLite 3 (WAL Mode)</div>
              <div className="text-[11px] text-[#10B981] font-medium mt-0.5">● Connected & Transactional</div>
            </div>

            <div className="bg-white p-3.5 rounded border border-[#E2E8F0] shadow-2xs">
              <div className="flex items-center gap-2 text-xs font-semibold text-[#64748B] uppercase tracking-wider mb-1">
                <ShieldCheck className="w-4 h-4 text-[#10B981]" />
                <span>Audit Security</span>
              </div>
              <div className="font-mono font-bold text-sm text-[#0F172A]">SHA-256 Hashed</div>
              <div className="text-[11px] text-[#10B981] font-medium mt-0.5">● Non-Repudiation Active</div>
            </div>

            <div className="bg-white p-3.5 rounded border border-[#E2E8F0] shadow-2xs">
              <div className="flex items-center gap-2 text-xs font-semibold text-[#64748B] uppercase tracking-wider mb-1">
                <WifiOff className="w-4 h-4 text-[#F59E0B]" />
                <span>Deployment Mode</span>
              </div>
              <div className="font-mono font-bold text-sm text-[#0F172A]">100% Offline Edge</div>
              <div className="text-[11px] text-[#64748B] font-medium mt-0.5">Zero Cloud API Calls</div>
            </div>

            <div className="bg-white p-3.5 rounded border border-[#E2E8F0] shadow-2xs">
              <div className="flex items-center gap-2 text-xs font-semibold text-[#64748B] uppercase tracking-wider mb-1">
                <UserCheck className="w-4 h-4 text-[#6366F1]" />
                <span>Active Operator</span>
              </div>
              <div className="font-mono font-bold text-sm text-[#0F172A]">{officerId}</div>
              <div className="text-[11px] text-[#64748B] font-medium mt-0.5">8-Hour Shift Authorized</div>
            </div>
          </div>

          {/* Inference Stack Specs */}
          <div className="bg-white p-4 rounded border border-[#E2E8F0] shadow-2xs space-y-2">
            <div className="text-xs font-bold text-[#0F172A] uppercase tracking-wider flex items-center gap-2">
              <Cpu className="w-4 h-4 text-[#0EA5E9]" />
              <span>Edge AI & Computer Vision Stack</span>
            </div>
            <ul className="text-xs text-[#475569] space-y-1.5 font-mono">
              <li className="flex justify-between border-b border-[#F1F5F9] pb-1">
                <span className="text-[#64748B]">Document Preprocessor:</span>
                <span className="font-semibold text-[#0F172A]">OpenCV 4 (Laplacian + HSV Glare)</span>
              </li>
              <li className="flex justify-between border-b border-[#F1F5F9] pb-1">
                <span className="text-[#64748B]">Document Classifier:</span>
                <span className="font-semibold text-[#0F172A]">YOLOv8 INT8 (ONNX Runtime)</span>
              </li>
              <li className="flex justify-between border-b border-[#F1F5F9] pb-1">
                <span className="text-[#64748B]">OCR Engine:</span>
                <span className="font-semibold text-[#0F172A]">PaddleOCR Offline INT8</span>
              </li>
              <li className="flex justify-between">
                <span className="text-[#64748B]">Cryptographic Checksums:</span>
                <span className="font-semibold text-[#0F172A]">ICAO 9303 Modulo-10 / 37</span>
              </li>
            </ul>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="bg-[#F1F5F9] px-6 py-3 border-t border-[#E2E8F0] flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 bg-[#0F172A] hover:bg-[#1E293B] text-white text-xs font-bold uppercase rounded tracking-wider cursor-pointer transition-colors"
          >
            Close Settings
          </button>
        </div>
      </div>
    </div>
  );
}
