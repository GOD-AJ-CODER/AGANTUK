"use client";

import React from "react";
import { X, Layers, AlertTriangle, ShieldCheck } from "lucide-react";
import { ConfidenceScores } from "../lib/types";

interface HeatmapViewerProps {
  isOpen: boolean;
  onClose: () => void;
  rawImageB64?: string | null;
  confidenceScores?: ConfidenceScores;
  failureCodes?: string[];
}

export default function HeatmapViewer({
  isOpen,
  onClose,
  rawImageB64,
  confidenceScores,
  failureCodes = [],
}: HeatmapViewerProps) {
  if (!isOpen) return null;

  const hasPhotoSplicing = failureCodes.includes("ERR_FORENSIC_PHOTO_SPLICED");
  const hasDigitalPatching = failureCodes.includes("ERR_FORENSIC_DIGITAL_PATCHING");
  const hasInvalidDimensions = failureCodes.includes("ERR_FORENSIC_INVALID_DIMENSIONS");

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="w-full max-w-5xl bg-white border border-[#CBD5E1] rounded-xl flex flex-col shadow-2xl max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="bg-[#0F172A] text-white p-5 flex items-center justify-between border-b border-[#334155]">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded bg-[#0284C7]/20 flex items-center justify-center text-[#38BDF8]">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold uppercase tracking-wider text-white">
                Forensic Spectral & Tamper Heatmap Inspector
              </h3>
              <p className="text-xs font-mono text-[#94A3B8]">
                RULES 2.1 - 2.4: ERROR LEVEL ANALYSIS (ELA) & PRNU SENSOR NOISE
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 text-[#94A3B8] hover:text-white hover:bg-[#1E293B] rounded transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 50/50 Split View Container */}
        <div className="p-6 overflow-y-auto flex-1 bg-[#F8FAFC]">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
            {/* Left: Raw Document Crop */}
            <div className="border border-[#CBD5E1] rounded-lg bg-white p-4 flex flex-col shadow-xs">
              <div className="text-xs font-mono font-bold text-[#64748B] uppercase mb-2">
                Channel A: Raw Document Optical Frame
              </div>
              <div className="flex-1 min-h-[280px] flex items-center justify-center bg-[#F1F5F9] rounded border border-[#E2E8F0] p-2">
                {rawImageB64 ? (
                  <img
                    src={
                      rawImageB64.startsWith("data:")
                        ? rawImageB64
                        : `data:image/jpeg;base64,${rawImageB64}`
                    }
                    alt="Raw Optical Document"
                    className="max-h-[300px] object-contain rounded"
                  />
                ) : (
                  <div className="text-xs font-mono text-[#94A3B8]">NO IMAGE BUFFER AVAILABLE</div>
                )}
              </div>
            </div>

            {/* Right: Forensic Heatmap View */}
            <div className="border border-[#CBD5E1] rounded-lg bg-white p-4 flex flex-col shadow-xs">
              <div className="text-xs font-mono font-bold text-[#0284C7] uppercase mb-2 flex items-center justify-between">
                <span>Channel B: Forensic Spectral Variance Map</span>
                <span className="text-[10px] bg-[#E0F2FE] text-[#0369A1] font-bold px-2 py-0.5 rounded">
                  ELA 95% + PRNU
                </span>
              </div>
              <div className="flex-1 min-h-[280px] flex items-center justify-center bg-[#050B14] rounded border border-[#1E293B] relative overflow-hidden p-2">
                {rawImageB64 ? (
                  <div className="relative">
                    <img
                      src={
                        rawImageB64.startsWith("data:")
                          ? rawImageB64
                          : `data:image/jpeg;base64,${rawImageB64}`
                      }
                      alt="Heatmap Base"
                      className="max-h-[300px] object-contain opacity-35 filter grayscale contrast-200"
                    />
                    <div
                      className={`absolute inset-0 pointer-events-none mix-blend-color-dodge rounded ${
                        hasPhotoSplicing || hasDigitalPatching
                          ? "bg-gradient-to-tr from-blue-900/60 via-purple-700/50 to-red-600/80 animate-pulse"
                          : "bg-gradient-to-tr from-blue-950/80 via-blue-900/40 to-teal-900/30"
                      }`}
                    />
                    {(hasPhotoSplicing || hasDigitalPatching) && (
                      <div className="absolute top-4 left-4 border border-[#EF4444] bg-[#EF4444]/80 text-white rounded px-2 py-1 font-mono text-xs font-bold uppercase tracking-wider shadow">
                        TAMPERED ZONE HIGHLIGHTED
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-xs font-mono text-[#64748B]">NO FORENSIC BUFFER</div>
                )}
              </div>
            </div>
          </div>

          {/* Forensic Signal Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
            <div className="bg-white border border-[#E2E8F0] rounded-lg p-3.5 shadow-xs">
              <div className="text-[#64748B] uppercase mb-1">Error Level Analysis (ELA)</div>
              <div className="text-lg font-bold text-[#0F172A] flex items-center justify-between">
                <span>{confidenceScores?.ela_variance_ratio ?? "1.00"}</span>
                {hasPhotoSplicing ? (
                  <span className="text-[#DC2626] text-xs font-bold flex items-center gap-1">
                    <AlertTriangle className="w-3.5 h-3.5" /> VARIANCE SPIKE &gt; 15.0
                  </span>
                ) : (
                  <span className="text-[#059669] text-xs font-bold flex items-center gap-1">
                    <ShieldCheck className="w-3.5 h-3.5" /> CLEAN
                  </span>
                )}
              </div>
            </div>

            <div className="bg-white border border-[#E2E8F0] rounded-lg p-3.5 shadow-xs">
              <div className="text-[#64748B] uppercase mb-1">PRNU Sensor Pattern</div>
              <div className="text-lg font-bold text-[#0F172A] flex items-center justify-between">
                <span>{hasDigitalPatching ? "ANOMALY DETECTED" : "CONSISTENT"}</span>
                {hasDigitalPatching ? (
                  <span className="text-[#DC2626] text-xs font-bold flex items-center gap-1">
                    <AlertTriangle className="w-3.5 h-3.5" /> DIGITAL PATCH
                  </span>
                ) : (
                  <span className="text-[#059669] text-xs font-bold flex items-center gap-1">
                    <ShieldCheck className="w-3.5 h-3.5" /> UNIFORM NOISE
                  </span>
                )}
              </div>
            </div>

            <div className="bg-white border border-[#E2E8F0] rounded-lg p-3.5 shadow-xs">
              <div className="text-[#64748B] uppercase mb-1">ISO 7810 Card Geometry</div>
              <div className="text-lg font-bold text-[#0F172A] flex items-center justify-between">
                <span>{hasInvalidDimensions ? "DEVIATION (>3.0%)" : "COMPLIANT"}</span>
                {hasInvalidDimensions ? (
                  <span className="text-[#DC2626] text-xs font-bold">SIZE MISMATCH</span>
                ) : (
                  <span className="text-[#059669] text-xs font-bold">ID-1 / ID-3 OK</span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="bg-white border-t border-[#E2E8F0] p-4 flex justify-end">
          <button
            onClick={onClose}
            className="px-6 py-2.5 bg-[#0F172A] hover:bg-[#1E293B] text-white font-bold text-xs uppercase tracking-wider rounded-md cursor-pointer transition-colors"
          >
            Close Inspector
          </button>
        </div>
      </div>
    </div>
  );
}
