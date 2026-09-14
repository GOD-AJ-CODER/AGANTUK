"use client";

import React, { useState } from "react";
import { X, AlertCircle, ShieldAlert, CheckCircle } from "lucide-react";
import { VerdictStatus } from "../lib/types";

interface OverrideModalProps {
  isOpen: boolean;
  onClose: () => void;
  verdict: VerdictStatus;
  docNumber?: string | null;
  officerId: string;
  onConfirmOverride: (justification: string) => void;
}

export default function OverrideModal({
  isOpen,
  onClose,
  verdict,
  docNumber,
  officerId,
  onConfirmOverride,
}: OverrideModalProps) {
  const [justification, setJustification] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  // Rule 7.4: Override is NEVER available for CRITICAL_SECURITY_ALERT
  const isForbidden = verdict === "CRITICAL_SECURITY_ALERT";
  const isValidLength = justification.trim().length > 15;
  const charsNeeded = Math.max(0, 16 - justification.trim().length);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isForbidden || !isValidLength) return;

    setIsSubmitting(true);
    setTimeout(() => {
      onConfirmOverride(justification.trim());
      setIsSubmitting(false);
      setJustification("");
      onClose();
    }, 400);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="w-full max-w-xl bg-white border border-[#CBD5E1] rounded-xl flex flex-col shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="bg-[#0F172A] text-white p-5 flex items-center justify-between border-b border-[#334155]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-[#F59E0B]/20 flex items-center justify-center text-[#F59E0B]">
              <AlertCircle className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold uppercase tracking-wide">
                Officer Discretionary Override
              </h3>
              <p className="text-xs font-mono text-[#94A3B8]">
                RULE 7.4: AUDIT-COMMITTED NON-REPUDIATION LOG
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

        {/* Content Body */}
        <div className="p-6">
          {isForbidden ? (
            <div className="bg-[#FEF2F2] border border-[#FCA5A5] rounded-lg p-5 flex items-start gap-3">
              <ShieldAlert className="w-6 h-6 text-[#DC2626] shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-bold text-[#991B1B] uppercase mb-1">
                  Manual Override Prohibited
                </h4>
                <p className="text-xs text-[#7F1D1D] leading-relaxed">
                  CRITICAL_SECURITY_ALERT cannot be overridden by station operators. This incident must
                  be escalated to a supervisory officer outside the terminal software.
                </p>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg p-3.5 text-xs">
                <div className="text-[#64748B] font-medium">Target Travel Credential:</div>
                <div className="text-[#0F172A] font-bold font-mono text-sm mt-0.5">
                  {docNumber || "ACTIVE PASSPORT CREDENTIAL"}
                </div>
                <div className="text-[#64748B] font-medium mt-2">Authorizing Officer ID:</div>
                <div className="text-[#0F172A] font-bold font-mono">{officerId}</div>
              </div>

              <div>
                <label className="block text-xs uppercase font-bold text-[#475569] mb-1">
                  Officer Operational Justification (Minimum 16 Characters)
                </label>
                <textarea
                  value={justification}
                  onChange={(e) => setJustification(e.target.value)}
                  placeholder="e.g. Visual secondary inspection verified valid consular sticker #40921"
                  rows={4}
                  className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg text-[#0F172A] p-3 text-sm focus:border-[#0EA5E9] focus:bg-white outline-none"
                />

                <div className="flex justify-between items-center text-xs mt-1.5 font-medium">
                  <span
                    className={
                      isValidLength
                        ? "text-[#059669] flex items-center gap-1"
                        : "text-[#DC2626]"
                    }
                  >
                    {isValidLength ? (
                      <>
                        <CheckCircle className="w-4 h-4" /> Justification requirement met
                      </>
                    ) : (
                      `Enter ${charsNeeded} more character${charsNeeded > 1 ? "s" : ""}`
                    )}
                  </span>
                  <span className="text-[#64748B] font-mono">
                    {justification.trim().length} / 16 chars
                  </span>
                </div>
              </div>

              <div className="pt-3 border-t border-[#E2E8F0] flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 border border-[#CBD5E1] bg-white hover:bg-[#F8FAFC] text-[#334155] rounded-md font-bold text-xs uppercase cursor-pointer"
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  disabled={!isValidLength || isSubmitting}
                  className="px-6 py-2 bg-[#D97706] hover:bg-[#B45309] disabled:opacity-30 disabled:pointer-events-none text-white rounded-md font-bold text-xs uppercase tracking-wider cursor-pointer transition-colors shadow-xs"
                >
                  {isSubmitting ? "Recording Override..." : "Authorize Manual Pass"}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
