"use client";

import React, { useState } from "react";
import { Fingerprint, ShieldCheck, ShieldAlert, LogOut, CheckCircle2 } from "lucide-react";
import { AuthSession } from "../lib/types";
import { loginWithFingerprint, clearSession } from "../lib/api";

interface FingerprintGateProps {
  session: AuthSession | null;
  onAuthenticated: (session: AuthSession) => void;
  onLogout: () => void;
}

export default function FingerprintGate({
  session,
  onAuthenticated,
  onLogout,
}: FingerprintGateProps) {
  const [scanning, setScanning] = useState(false);
  const [badgeInput, setBadgeInput] = useState("OFF-8472");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleScan = async () => {
    setScanning(true);
    setErrorMsg(null);
    try {
      await new Promise((r) => setTimeout(r, 500));
      const newSession = await loginWithFingerprint(badgeInput);
      onAuthenticated(newSession);
    } catch (err: any) {
      setErrorMsg(err.message || "Biometric sensor timeout. Re-place finger.");
    } finally {
      setScanning(false);
    }
  };

  // Persistent 8-Hour Shift Session Banner
  if (session) {
    return (
      <div className="w-full bg-white border border-[#E2E8F0] rounded-lg p-3.5 shadow-xs flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-[#ECFDF5] border border-[#A7F3D0] flex items-center justify-center text-[#059669]">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[11px] font-semibold text-[#64748B] uppercase tracking-wider">
              Active Shift Operator
            </div>
            <div className="text-sm font-bold text-[#0F172A]">
              {session.full_name} <span className="text-[#0EA5E9] font-mono">[{session.badge_number}]</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-[#F8FAFC] border border-[#E2E8F0] rounded text-xs font-semibold text-[#334155]">
            <span className="w-2 h-2 rounded-full bg-[#10B981] animate-pulse"></span>
            <span>8-HOUR SHIFT AUTHORIZED</span>
          </div>

          <button
            onClick={() => {
              clearSession();
              onLogout();
            }}
            className="px-3.5 py-1.5 border border-[#CBD5E1] hover:bg-[#F1F5F9] rounded text-xs font-bold text-[#475569] flex items-center gap-1.5 cursor-pointer transition-colors"
          >
            <LogOut className="w-3.5 h-3.5 text-[#EF4444]" />
            <span>End Shift</span>
          </button>
        </div>
      </div>
    );
  }

  // Unauthenticated Biometric Lock Screen
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-md bg-white border border-[#CBD5E1] rounded-xl p-8 flex flex-col items-center text-center shadow-lg">
        <div className="w-18 h-18 rounded-2xl bg-[#F0F9FF] border-2 border-[#0EA5E9] flex items-center justify-center mb-5 text-[#0EA5E9] shadow-inner">
          <Fingerprint className="w-10 h-10" />
        </div>

        <h1 className="text-xl font-black uppercase tracking-wider text-[#0F172A] mb-1">
          Officer Biometric Sign-In
        </h1>
        <p className="text-xs text-[#64748B] mb-6">
          AGANTUK FRONTLINE TERMINAL // 8-HOUR SHIFT AUTHORIZATION
        </p>

        {errorMsg && (
          <div className="w-full bg-[#FEF2F2] border border-[#FCA5A5] text-[#B91C1C] p-3 text-xs rounded-md mb-4 text-left flex items-center gap-2 font-medium">
            <ShieldAlert className="w-4 h-4 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        <div className="w-full mb-5 text-left">
          <label className="block text-xs uppercase font-bold text-[#475569] mb-1">
            Officer Badge / Station ID
          </label>
          <input
            type="text"
            value={badgeInput}
            onChange={(e) => setBadgeInput(e.target.value.toUpperCase())}
            className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded-md text-[#0F172A] font-mono p-3 focus:border-[#0EA5E9] focus:bg-white outline-none text-sm font-semibold"
          />
        </div>

        <button
          onClick={handleScan}
          disabled={scanning}
          className="w-full min-h-[52px] bg-[#0F172A] hover:bg-[#1E293B] text-white font-bold text-sm uppercase tracking-wider rounded-lg flex items-center justify-center gap-2.5 cursor-pointer disabled:opacity-50 transition-colors shadow-sm"
        >
          <Fingerprint className={`w-5 h-5 ${scanning ? "animate-pulse text-[#38BDF8]" : ""}`} />
          <span>{scanning ? "Authenticating Biometrics..." : "Authorize 8-Hour Shift"}</span>
        </button>

        <div className="mt-6 flex items-center gap-2 text-[11px] text-[#64748B]">
          <ShieldCheck className="w-4 h-4 text-[#10B981]" />
          <span>FIPS 140-2 HARDWARE BIOMETRIC ENCLAVE READY</span>
        </div>
      </div>
    </div>
  );
}
