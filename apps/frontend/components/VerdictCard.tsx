"use client";

import React, { useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  XOctagon,
  ShieldAlert,
  Hash,
  Copy,
  Layers,
  ChevronDown,
  ChevronUp,
  Info,
  Check,
} from "lucide-react";
import { VerificationResponse, VerdictStatus } from "../lib/types";
import { translateFailureCode } from "../lib/language";

interface VerdictCardProps {
  result: VerificationResponse;
  warpedImageB64?: string | null;
  onOpenHeatmap: () => void;
  onOpenOverride: () => void;
  onNextScan: () => void;
}

export default function VerdictCard({
  result,
  warpedImageB64,
  onOpenHeatmap,
  onOpenOverride,
  onNextScan,
}: VerdictCardProps) {
  const { verdict, failure_codes, extracted_fields, confidence_scores, audit_hash, log_id } =
    result;

  const [copied, setCopied] = useState(false);
  const [expandedTechCodes, setExpandedTechCodes] = useState<Record<string, boolean>>({});

  const toggleTechDetails = (code: string) => {
    setExpandedTechCodes((prev) => ({
      ...prev,
      [code]: !prev[code],
    }));
  };

  const copyHash = () => {
    if (audit_hash) {
      navigator.clipboard.writeText(audit_hash);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // ── Full-screen Lockout for CRITICAL_SECURITY_ALERT ──
  if (verdict === "CRITICAL_SECURITY_ALERT") {
    return (
      <div className="fixed inset-0 z-50 bg-[#7F1D1D] p-6 md:p-12 flex flex-col items-center justify-center animate-tactical-strobe">
        <div className="w-full max-w-4xl bg-white rounded-xl border-4 border-[#DC2626] p-8 md:p-12 flex flex-col items-center text-center shadow-2xl text-[#0F172A]">
          <div className="w-24 h-24 bg-[#DC2626] rounded-full flex items-center justify-center mb-6 shadow-lg">
            <ShieldAlert className="w-14 h-14 text-white" />
          </div>

          <div className="w-full bg-[#DC2626] text-white py-4 px-6 rounded-lg text-2xl md:text-4xl font-black uppercase tracking-wider mb-6 shadow-sm">
            ⛔ CRITICAL SECURITY ALERT — LOCKDOWN GATE
          </div>

          <h2 className="text-xl md:text-2xl font-black text-[#991B1B] uppercase mb-4">
            FLAGGED WATCHLIST HIT DETECTED
          </h2>

          <div className="w-full bg-[#FEF2F2] border-2 border-[#F87171] rounded-lg p-5 text-left mb-6 space-y-3">
            <div className="text-sm font-bold text-[#991B1B]">
              ALERT REASON: Target credential exact-matches an active national security watchlist.
            </div>
            {extracted_fields?.doc_number && (
              <div className="text-sm text-[#0F172A] font-semibold">
                Passport / ID Number:{" "}
                <span className="font-mono text-base font-black text-[#DC2626] bg-white px-2 py-0.5 rounded border border-[#FCA5A5]">
                  {extracted_fields.doc_number}
                </span>{" "}
                {extracted_fields.full_name && `(${extracted_fields.full_name})`}
              </div>
            )}
            <div className="text-xs text-[#7F1D1D] leading-relaxed font-medium">
              OPERATING DIRECTIVE: Do not clear passenger. Maintain custody of travel document.
              Officer manual override is strictly disabled by system rule.
            </div>
          </div>

          {audit_hash && (
            <div className="w-full bg-[#F1F5F9] border border-[#CBD5E1] rounded p-3 text-xs font-mono text-left mb-6 break-all">
              <span className="font-bold text-[#475569]">NON-REPUDIATION AUDIT RECORD:</span>{" "}
              <span className="text-[#0F172A] font-semibold">{audit_hash}</span>
            </div>
          )}

          <div className="w-full p-4 bg-[#FEE2E2] border-2 border-[#EF4444] rounded text-sm font-bold text-[#991B1B] uppercase">
            Escalate directly to shift supervisor workstation
          </div>
        </div>
      </div>
    );
  }

  // ── Hero Banner Configuration per verdict ──
  const heroConfig = {
    PASS: {
      bannerText: "✅ CLEAR — PASSPORT VERIFIED",
      bannerBg: "bg-[#059669]", // Vibrant Green
      cardBorder: "border-[#10B981]",
      cardShadow: "shadow-emerald-100",
      icon: <CheckCircle2 className="w-10 h-10 text-white" />,
      subtext: "All physical forensics, Modulo-10 checksums, and date timelines verified.",
    },
    MANUAL_REVIEW: {
      bannerText: "⚠️ ATTENTION — MANUAL CHECK REQUIRED",
      bannerBg: "bg-[#D97706]", // Vibrant Amber
      cardBorder: "border-[#F59E0B]",
      cardShadow: "shadow-amber-100",
      icon: <AlertTriangle className="w-10 h-10 text-white" />,
      subtext: "Low optical confidence or lighting distortion detected. Visual inspection needed.",
    },
    FLAGGED: {
      bannerText: "❌ REJECTED — TAMPERED OR FAKE DOCUMENT",
      bannerBg: "bg-[#DC2626]", // Vibrant Red
      cardBorder: "border-[#EF4444]",
      cardShadow: "shadow-red-100",
      icon: <XOctagon className="w-10 h-10 text-white" />,
      subtext: "Mathematical mismatch, temporal contradiction, or forensic alteration detected.",
    },
  }[verdict] || {
    bannerText: `VERDICT: ${verdict}`,
    bannerBg: "bg-[#475569]",
    cardBorder: "border-[#64748B]",
    cardShadow: "",
    icon: <Info className="w-10 h-10 text-white" />,
    subtext: "",
  };

  return (
    <div
      className={`w-full bg-white border-2 ${heroConfig.cardBorder} rounded-xl overflow-hidden shadow-xl ${heroConfig.cardShadow} flex flex-col`}
    >
      {/* ── Massive Hero Verdict Banner ── */}
      <div className={`${heroConfig.bannerBg} text-white px-6 py-5 flex flex-wrap items-center justify-between gap-4`}>
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-full bg-white/20 flex items-center justify-center shrink-0">
            {heroConfig.icon}
          </div>
          <div>
            <h2 className="text-2xl md:text-3xl font-black tracking-wide uppercase">
              {heroConfig.bannerText}
            </h2>
            <p className="text-xs md:text-sm text-white/90 font-medium mt-0.5">
              {heroConfig.subtext}
            </p>
          </div>
        </div>

        {/* Hero Banner Controls */}
        <div className="flex items-center gap-3">
          <button
            onClick={onOpenHeatmap}
            className="px-4 py-2.5 rounded-lg bg-white text-[#0F172A] hover:bg-[#F8FAFC] font-bold text-xs uppercase flex items-center gap-2 cursor-pointer shadow-xs transition-colors"
          >
            <Layers className="w-4 h-4 text-[#0EA5E9]" />
            <span>Forensic Heatmap</span>
          </button>

          {verdict === "FLAGGED" && (
            <button
              onClick={onOpenOverride}
              className="px-4 py-2.5 rounded-lg bg-white/20 hover:bg-white/30 text-white border border-white/40 font-bold text-xs uppercase cursor-pointer transition-colors"
            >
              Manual Override
            </button>
          )}

          <button
            onClick={onNextScan}
            className="px-6 py-2.5 rounded-lg bg-white text-[#0F172A] hover:bg-[#F1F5F9] font-black text-xs uppercase tracking-wider cursor-pointer shadow-md transition-all"
          >
            Next Document
          </button>
        </div>
      </div>

      <div className="p-6 space-y-6">
        {/* ── Plain-English Failure Explanations (If any issues found) ── */}
        {failure_codes.length > 0 && (
          <div className="space-y-3">
            <div className="text-xs font-black text-[#64748B] uppercase tracking-wider">
              Identified Credential Issues ({failure_codes.length})
            </div>

            <div className="grid grid-cols-1 gap-3">
              {failure_codes.map((code) => {
                const explanation = translateFailureCode(code, {
                  expiryDate: extracted_fields?.expiry_date,
                  docNumber: extracted_fields?.doc_number,
                });
                const isExpanded = !!expandedTechCodes[code];

                const badgeColors = {
                  critical: "bg-[#FEF2F2] border-[#FCA5A5] text-[#991B1B]",
                  high: "bg-[#FEF2F2] border-[#FCA5A5] text-[#991B1B]",
                  medium: "bg-[#FFFBEB] border-[#FCD34D] text-[#92400E]",
                  low: "bg-[#F8FAFC] border-[#CBD5E1] text-[#475569]",
                }[explanation.severity];

                return (
                  <div
                    key={code}
                    className={`border rounded-lg p-4 transition-all ${badgeColors}`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="space-y-1">
                        <div className="text-base font-bold text-[#0F172A] flex items-center gap-2">
                          <span className="w-2.5 h-2.5 rounded-full bg-[#EF4444]" />
                          {explanation.title}
                        </div>
                        <p className="text-xs text-[#334155] font-medium leading-relaxed">
                          {explanation.summary}
                        </p>
                      </div>

                      {/* Expandable Inspector Technical Details Button */}
                      <button
                        onClick={() => toggleTechDetails(code)}
                        className="px-2.5 py-1 text-[11px] font-mono font-semibold rounded border border-[#CBD5E1] bg-white text-[#475569] hover:bg-[#F1F5F9] flex items-center gap-1 cursor-pointer"
                      >
                        <span>Inspector Technical Details</span>
                        {isExpanded ? (
                          <ChevronUp className="w-3.5 h-3.5" />
                        ) : (
                          <ChevronDown className="w-3.5 h-3.5" />
                        )}
                      </button>
                    </div>

                    {/* Action Guideline */}
                    <div className="mt-3 pt-2.5 border-t border-black/10 text-xs font-semibold text-[#0F172A] flex items-center gap-1.5">
                      <span className="text-[#0EA5E9] font-bold">Action for Officer:</span>
                      <span>{explanation.action}</span>
                    </div>

                    {/* Technical Rule Code Drawer */}
                    {isExpanded && (
                      <div className="mt-3 p-3 bg-[#0F172A] text-white rounded font-mono text-[11px] space-y-1">
                        <div className="flex justify-between">
                          <span className="text-[#94A3B8]">Security Rule Code:</span>
                          <span className="text-[#38BDF8] font-bold">{code}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[#94A3B8]">Algorithm / Standard:</span>
                          <span>ICAO Doc 9303 / ISO 7810 / Modulo Math</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-[#94A3B8]">Automated Stage:</span>
                          <span>Stage 4 Mathematical & Logical Rule Engine</span>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Document Information Card Grid ── */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Extracted Details */}
          <div className="md:col-span-2 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg p-5">
            <div className="text-xs uppercase font-bold text-[#64748B] tracking-wider mb-4 border-b border-[#E2E8F0] pb-2">
              Extracted Traveler Credential Information
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-xs text-[#64748B] font-medium uppercase">Passport Number</div>
                <div className="font-mono text-xl font-black text-[#0F172A] mt-0.5">
                  <span className="bg-white px-2 py-0.5 rounded border border-[#CBD5E1] text-[#0284C7]">
                    {extracted_fields?.doc_number || "—"}
                  </span>
                </div>
              </div>

              <div>
                <div className="text-xs text-[#64748B] font-medium uppercase">Traveler Name</div>
                <div className="text-base font-bold text-[#0F172A] mt-1">
                  {extracted_fields?.full_name ||
                    `${extracted_fields?.given_names || ""} ${extracted_fields?.surname || ""}`.trim() ||
                    "—"}
                </div>
              </div>

              <div>
                <div className="text-xs text-[#64748B] font-medium uppercase">Date of Birth</div>
                <div className="font-mono text-sm font-bold text-[#0F172A] mt-0.5">
                  {extracted_fields?.date_of_birth || "—"}
                </div>
              </div>

              <div>
                <div className="text-xs text-[#64748B] font-medium uppercase">Expiry Date</div>
                <div className="font-mono text-sm font-bold text-[#0F172A] mt-0.5">
                  {extracted_fields?.expiry_date || "—"}
                </div>
              </div>

              <div>
                <div className="text-xs text-[#64748B] font-medium uppercase">Nationality / Country</div>
                <div className="font-mono text-sm font-bold text-[#0F172A] mt-0.5">
                  {extracted_fields?.nationality || extracted_fields?.issuing_country || "—"}
                </div>
              </div>

              <div>
                <div className="text-xs text-[#64748B] font-medium uppercase">Document Category</div>
                <div className="font-mono text-sm font-bold text-[#0F172A] mt-0.5">
                  {result.doc_type_detected || "PASSPORT"}
                </div>
              </div>
            </div>
          </div>

          {/* Clarity & Confidence Scores */}
          <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg p-5 flex flex-col justify-between">
            <div>
              <div className="text-xs uppercase font-bold text-[#64748B] tracking-wider mb-3 border-b border-[#E2E8F0] pb-2">
                Scanner Quality & Confidence
              </div>

              <div className="space-y-3 font-mono text-xs">
                <div className="flex justify-between items-center">
                  <span className="text-[#64748B]">Image Clarity:</span>
                  <span className="font-bold text-[#0F172A] bg-white px-2 py-0.5 rounded border border-[#E2E8F0]">
                    {confidence_scores?.laplacian_variance ?? "—"}
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-[#64748B]">OCR Match Score:</span>
                  <span className="font-bold text-[#0F172A] bg-white px-2 py-0.5 rounded border border-[#E2E8F0]">
                    {confidence_scores?.ocr_average != null
                      ? `${(confidence_scores.ocr_average * 100).toFixed(1)}%`
                      : "—"}
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-[#64748B]">ELA Variance:</span>
                  <span className="font-bold text-[#0F172A] bg-white px-2 py-0.5 rounded border border-[#E2E8F0]">
                    {confidence_scores?.ela_variance_ratio ?? "—"}
                  </span>
                </div>
              </div>
            </div>

            {warpedImageB64 && (
              <div className="mt-4 border border-[#CBD5E1] rounded bg-white p-1">
                <img
                  src={
                    warpedImageB64.startsWith("data:")
                      ? warpedImageB64
                      : `data:image/jpeg;base64,${warpedImageB64}`
                  }
                  alt="Scanned Document"
                  className="w-full h-20 object-cover rounded"
                />
              </div>
            )}
          </div>
        </div>

        {/* ── Non-Repudiation Cryptographic Hash Banner ── */}
        {audit_hash && (
          <div className="bg-[#F1F5F9] border border-[#CBD5E1] rounded-lg p-3.5 flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
            <div className="flex items-center gap-2 text-[#475569]">
              <Hash className="w-4 h-4 text-[#0EA5E9]" />
              <span className="font-bold">NON-REPUDIATION AUDIT RECORD SHA-256:</span>
              <span className="text-[#0F172A] font-bold select-all bg-white px-2 py-0.5 rounded border border-[#E2E8F0]">
                {audit_hash}
              </span>
            </div>

            <button
              onClick={copyHash}
              className="px-3 py-1.5 bg-white border border-[#CBD5E1] hover:bg-[#F8FAFC] rounded text-[#0F172A] font-bold flex items-center gap-1.5 cursor-pointer shadow-2xs"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-[#10B981]" />
                  <span className="text-[#10B981]">COPIED</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5 text-[#64748B]" />
                  <span>COPY HASH</span>
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
