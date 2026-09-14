"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  UploadCloud,
  FileSearch,
  AlertTriangle,
  Sparkles,
  Camera,
  RefreshCw,
  Sliders,
  Check,
} from "lucide-react";
import FingerprintGate from "../../components/FingerprintGate";
import VerdictCard from "../../components/VerdictCard";
import HeatmapViewer from "../../components/HeatmapViewer";
import OverrideModal from "../../components/OverrideModal";
import { AuthSession, VerificationResponse } from "../../lib/types";
import { getStoredSession, processVerification } from "../../lib/api";

// Sample standard synthetic test passport (clean ID-3)
const SAMPLE_VALID_PASSPORT_B64 =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAzQAAAJYAQMAAABw+65IAAAABlBMVEUAAAAAAAClZ7nPAAAAAXRSTlMAQObYZgAAAFNJREFUeNrtwTEBAAAAwqD1T20ND6AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA8Aae4AABl2H8qgAAAABJRU5ErkJggg==";

export default function ScanPage() {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [imageB64, setImageB64] = useState<string | null>(null);
  const [declaredType, setDeclaredType] = useState("PASSPORT");
  const [terminalId, setTerminalId] = useState("TERMINAL-GATE-01");

  // Quality warnings
  const [blurWarning, setBlurWarning] = useState<boolean>(false);
  const [glareWarning, setGlareWarning] = useState<boolean>(false);

  // Staged progress state (No spinners — design.md §5)
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [progressStage, setProgressStage] = useState<number>(0);
  const [stageName, setStageName] = useState<string>("");

  // Result and Modals
  const [result, setResult] = useState<VerificationResponse | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [isHeatmapOpen, setIsHeatmapOpen] = useState(false);
  const [isOverrideOpen, setIsOverrideOpen] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setSession(getStoredSession());
  }, []);

  // Handle File Upload
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      const b64 = reader.result as string;
      setImageB64(b64);
      setResult(null);
      setErrorText(null);
      setBlurWarning(false);
      setGlareWarning(false);
    };
    reader.readAsDataURL(file);
  };

  // Trigger staged verification
  const executeVerification = async (
    customPayload?: { mrz_lines?: string[]; viz_fields?: any }
  ) => {
    if (!imageB64) {
      setErrorText("Select or capture a document image before processing.");
      return;
    }

    setIsProcessing(true);
    setResult(null);
    setErrorText(null);

    // Staged progress bar stepping through named stages (design.md §5)
    // 1. Ingestion / Pre-Processing
    setProgressStage(1);
    setStageName("Pre-Processing & Quality Gates...");
    await new Promise((r) => setTimeout(r, 250));

    // 2. Forensics Engine
    setProgressStage(2);
    setStageName("Forensics Engine (ELA, PRNU, Aspect Ratio)...");
    await new Promise((r) => setTimeout(r, 300));

    // 3. OCR & MRZ Extraction
    setProgressStage(3);
    setStageName("OCR Extraction & Modulo-10 / 37 Engine...");
    await new Promise((r) => setTimeout(r, 300));

    // 4. Watchlist & Chronological Logic
    setProgressStage(4);
    setStageName("Chronological Rules & SQLite Watchlist Passback...");
    await new Promise((r) => setTimeout(r, 200));

    try {
      const res = await processVerification(
        imageB64,
        declaredType,
        terminalId,
        customPayload?.mrz_lines,
        customPayload?.viz_fields
      );
      setResult(res);
    } catch (err: any) {
      setErrorText(err.message || "Verification request failed.");
    } finally {
      setIsProcessing(false);
      setProgressStage(0);
      setStageName("");
    }
  };

  // Quick Preset Scenarios for Rapid Field Testing
  const loadScenario = (type: "valid" | "expired" | "checksum_tamper" | "watchlist") => {
    setImageB64(SAMPLE_VALID_PASSPORT_B64);
    setResult(null);
    setErrorText(null);

    const docNum = `P${Math.floor(10000000 + Math.random() * 90000000)}`;

    if (type === "valid") {
      const line1 = "P<UTODOE<<JANE<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<";
      const line2 = "L898902C36UTO8507125F3001019<<<<<<<<<<<<<<04";
      executeVerification({
        mrz_lines: [line1, line2],
        viz_fields: {
          doc_number: "L898902C3",
          full_name: "JANE DOE",
          date_of_birth: "1985-07-12",
          expiry_date: "2030-01-01",
        },
      });
    } else if (type === "expired") {
      const line1 = "P<UTOSMITH<<JOHN<<<<<<<<<<<<<<<<<<<<<<<<<<<<";
      const line2 = `${docNum}6UTO8001014M2001015<<<<<<<<<<<<<<00`;
      executeVerification({
        mrz_lines: [line1, line2],
        viz_fields: {
          doc_number: docNum,
          full_name: "JOHN SMITH",
          date_of_birth: "1980-01-01",
          expiry_date: "2020-01-01", // Expired
        },
      });
    } else if (type === "checksum_tamper") {
      const line1 = "P<UTOFORGER<<BAD<<<<<<<<<<<<<<<<<<<<<<<<<<<<";
      // Invalid check digit 9 instead of calculated
      const line2 = `${docNum}9UTO8001014M3001015<<<<<<<<<<<<<<00`;
      executeVerification({
        mrz_lines: [line1, line2],
        viz_fields: {
          doc_number: docNum,
          full_name: "BAD FORGER",
          date_of_birth: "1980-01-01",
          expiry_date: "2030-01-01",
        },
      });
    } else if (type === "watchlist") {
      const line1 = "P<UTOWANTED<<PERSON<<<<<<<<<<<<<<<<<<<<<<<<<";
      // WL-1234567 is pre-seeded in database/local.db
      const line2 = "WL12345670UTO8507125M3001019<<<<<<<<<<<<<<00";
      executeVerification({
        mrz_lines: [line1, line2],
        viz_fields: {
          doc_number: "WL-1234567",
          full_name: "WANTED PERSON",
          date_of_birth: "1985-07-12",
          expiry_date: "2030-01-01",
        },
      });
    }
  };

  const resetScanner = () => {
    setImageB64(null);
    setResult(null);
    setErrorText(null);
    setBlurWarning(false);
    setGlareWarning(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // Render Staged Blocky Progress Bar: [██████░░░░]
  const renderStagedProgress = () => {
    const blocks = ["░", "░", "░", "░"];
    for (let i = 0; i < progressStage; i++) {
      blocks[i] = "█";
    }
    return (
      <div className="w-full bg-white border-2 border-[#16A34A] p-6 text-center shadow-lg rounded-xl">
        <div className="font-mono text-3xl font-black text-[#16A34A] tracking-widest mb-3">
          [{blocks.join("")}]
        </div>
        <div className="text-lg font-bold uppercase text-[#0F172A] tracking-wider">
          {stageName || "Processing Document..."}
        </div>
        <div className="text-xs font-mono text-[#64748B] mt-2">
          STAGE {progressStage} OF 4 // LATENCY BUDGET: &lt;1,500ms
        </div>
      </div>
    );
  };

  return (
    <div className="w-full flex flex-col gap-6">
      {/* Officer Session Banner */}
      <FingerprintGate
        session={session}
        onAuthenticated={(s) => setSession(s)}
        onLogout={() => setSession(null)}
      />

      {/* Main Scanner Cockpit */}
      <div className="w-full flex flex-col gap-6">
        {/* Progress Bar View (Active during scan) */}
        {isProcessing && renderStagedProgress()}

        {/* Verdict Hero Card (When completed) */}
        {!isProcessing && result && (
          <VerdictCard
            result={result}
            warpedImageB64={imageB64}
            onOpenHeatmap={() => setIsHeatmapOpen(true)}
            onOpenOverride={() => setIsOverrideOpen(true)}
            onNextScan={resetScanner}
          />
        )}

        {/* Scanner Input / Document Capture View (When no result) */}
        {!isProcessing && !result && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Capture Cockpit (2 cols) */}
            <div className="lg:col-span-2 bg-white border border-[#CBD5E1] rounded-xl p-6 shadow-sm flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between border-b border-[#E2E8F0] pb-3 mb-4">
                  <div className="text-sm font-bold uppercase tracking-wider text-[#0F172A] flex items-center gap-2">
                    <Camera className="w-5 h-5 text-[#0284C7]" />
                    <span>Document Feed / Capture Terminal</span>
                  </div>
                  <div className="text-xs font-mono text-[#64748B]">INPUT CHANNEL: PRIMARY</div>
                </div>

                {/* Dropzone / Preview Frame */}
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full min-h-[360px] border-2 border-dashed border-[#CBD5E1] hover:border-[#0284C7] bg-[#F8FAFC] rounded-lg flex flex-col items-center justify-center p-6 text-center cursor-pointer transition-colors"
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    onChange={handleFileUpload}
                    className="hidden"
                  />

                  {imageB64 ? (
                    <div className="flex flex-col items-center gap-4">
                      <img
                        src={imageB64}
                        alt="Document Upload Preview"
                        className="max-h-[280px] max-w-full object-contain border border-[#CBD5E1] rounded-md shadow-sm"
                      />
                      <span className="font-mono text-xs text-[#16A34A] font-bold uppercase">
                        ✓ Image Ready for Inspection
                      </span>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-3">
                      <div className="w-16 h-16 border border-[#CBD5E1] bg-white rounded-full flex items-center justify-center shadow-sm">
                        <UploadCloud className="w-8 h-8 text-[#0284C7]" />
                      </div>
                      <div className="text-base font-bold text-[#0F172A] uppercase tracking-wide">
                        Click or Drop Document Image Here to Scan
                      </div>
                      <div className="text-xs font-mono text-[#64748B]">
                        JPEG, PNG, OR WEBP // 100% OFFLINE EDGE INFERENCE
                      </div>
                    </div>
                  )}
                </div>

                {/* Real-time Quality Indicators (Blur, Glare) */}
                {(blurWarning || glareWarning) && (
                  <div className="mt-4 bg-[#FEF3C7] border border-[#F59E0B] text-[#92400E] rounded-lg p-3 text-xs font-medium flex items-center gap-3">
                    <AlertTriangle className="w-5 h-5 shrink-0 text-[#D97706]" />
                    <div>
                      {blurWarning && "Image appears slightly blurry. Please ensure clear focus. "}
                      {glareWarning && "Glare detected over text area. Adjust document angle."}
                    </div>
                  </div>
                )}

                {errorText && (
                  <div className="mt-4 bg-[#FEE2E2] border border-[#EF4444] text-[#991B1B] rounded-lg p-3 text-xs font-mono">
                    ERROR: {errorText}
                  </div>
                )}
              </div>

              {/* Action Buttons */}
              <div className="mt-6 flex flex-wrap gap-4 pt-4 border-t border-[#E2E8F0]">
                <button
                  onClick={() => executeVerification()}
                  disabled={!imageB64}
                  className="flex-1 touch-target bg-[#0F172A] hover:bg-[#1E293B] disabled:opacity-40 disabled:pointer-events-none text-white font-bold text-base uppercase tracking-wider rounded-lg flex items-center justify-center gap-3 cursor-pointer transition-colors shadow-md"
                >
                  <FileSearch className="w-6 h-6 text-[#38BDF8]" />
                  <span>Execute Verification Pipeline</span>
                </button>

                <button
                  onClick={resetScanner}
                  className="touch-target-sm px-6 border border-[#CBD5E1] hover:bg-[#F1F5F9] text-[#0F172A] font-bold text-xs uppercase rounded-lg cursor-pointer transition-colors"
                >
                  Reset
                </button>
              </div>
            </div>

            {/* Tactical Control & Rapid Testing Scenarios (1 col) */}
            <div className="bg-white border border-[#CBD5E1] rounded-xl p-6 shadow-sm flex flex-col justify-between">
              <div>
                <div className="text-sm font-bold uppercase tracking-wider text-[#0F172A] border-b border-[#E2E8F0] pb-3 mb-4 flex items-center gap-2">
                  <Sliders className="w-5 h-5 text-[#0284C7]" />
                  <span>Terminal Configuration</span>
                </div>

                <div className="space-y-4 mb-6">
                  <div>
                    <label className="block text-xs uppercase font-bold text-[#64748B] mb-1">
                      Declared Credential Type
                    </label>
                    <select
                      value={declaredType}
                      onChange={(e) => setDeclaredType(e.target.value)}
                      className="w-full bg-[#F8FAFC] border border-[#CBD5E1] text-[#0F172A] font-mono p-3 rounded-lg focus:border-[#0284C7] outline-none touch-target-sm"
                    >
                      <option value="PASSPORT">PASSPORT (ICAO TD3)</option>
                      <option value="NATIONAL_ID">NATIONAL ID (TD1 / TD2)</option>
                      <option value="VISA">VISA (ICAO FORMAT-V)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs uppercase font-bold text-[#64748B] mb-1">
                      Scanning Gate / Terminal ID
                    </label>
                    <input
                      type="text"
                      value={terminalId}
                      onChange={(e) => setTerminalId(e.target.value)}
                      className="w-full bg-[#F8FAFC] border border-[#CBD5E1] text-[#0F172A] font-mono p-3 text-sm rounded-lg focus:border-[#0284C7] outline-none touch-target-sm"
                    />
                  </div>
                </div>

                {/* Preset Operational Scenarios */}
                <div className="border-t border-[#E2E8F0] pt-4">
                  <div className="text-xs uppercase font-bold text-[#64748B] tracking-wider mb-3">
                    Rapid Verification Scenarios
                  </div>

                  <div className="grid grid-cols-1 gap-2.5">
                    <button
                      onClick={() => loadScenario("valid")}
                      className="touch-target-sm p-3 bg-[#F0FDF4] border border-[#86EFAC] hover:bg-[#DCFCE7] rounded-lg text-left cursor-pointer transition-colors"
                    >
                      <div className="text-xs font-bold text-[#166534] uppercase">
                        1. Authentic Passport
                      </div>
                      <div className="font-mono text-[11px] text-[#15803D]">
                        Valid checksums, clean forensics, PASS verdict
                      </div>
                    </button>

                    <button
                      onClick={() => loadScenario("expired")}
                      className="touch-target-sm p-3 bg-[#FEF2F2] border border-[#FCA5A5] hover:bg-[#FEE2E2] rounded-lg text-left cursor-pointer transition-colors"
                    >
                      <div className="text-xs font-bold text-[#991B1B] uppercase">
                        2. Chronological Expiry Failure
                      </div>
                      <div className="font-mono text-[11px] text-[#B91C1C]">
                        Expired document → Human logic translation
                      </div>
                    </button>

                    <button
                      onClick={() => loadScenario("checksum_tamper")}
                      className="touch-target-sm p-3 bg-[#FFFBEB] border border-[#FDE68A] hover:bg-[#FEF3C7] rounded-lg text-left cursor-pointer transition-colors"
                    >
                      <div className="text-xs font-bold text-[#92400E] uppercase">
                        3. Checksum Tamper Attempt
                      </div>
                      <div className="font-mono text-[11px] text-[#B45309]">
                        Altered Passport # → Modulo check error
                      </div>
                    </button>

                    <button
                      onClick={() => loadScenario("watchlist")}
                      className="touch-target-sm p-3 bg-[#FEF2F2] border border-[#EF4444] hover:bg-[#FEE2E2] rounded-lg text-left cursor-pointer transition-colors"
                    >
                      <div className="text-xs font-bold text-[#991B1B] uppercase">
                        4. Watchlist Hit (CRITICAL)
                      </div>
                      <div className="font-mono text-[11px] text-[#B91C1C]">
                        Blacklisted document → Full Lockdown Gate Alert
                      </div>
                    </button>
                  </div>
                </div>
              </div>

              <div className="mt-6 pt-3 border-t border-[#E2E8F0] text-[11px] font-mono text-[#94A3B8]">
                OFFLINE EDGE ENGINE // LOCAL ONLY // SHA-256 AUDITED
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Forensic Heatmap Modal */}
      <HeatmapViewer
        isOpen={isHeatmapOpen}
        onClose={() => setIsHeatmapOpen(false)}
        rawImageB64={imageB64}
        confidenceScores={result?.confidence_scores}
        failureCodes={result?.failure_codes}
      />

      {/* Officer Manual Override Modal */}
      {result && (
        <OverrideModal
          isOpen={isOverrideOpen}
          onClose={() => setIsOverrideOpen(false)}
          verdict={result.verdict}
          docNumber={result.extracted_fields?.doc_number}
          officerId={session?.officer_id || "OFFICER-LOCAL"}
          onConfirmOverride={(justification) => {
            alert(`Manual override committed to audit trail with justification: "${justification}"`);
            resetScanner();
          }}
        />
      )}
    </div>
  );
}
