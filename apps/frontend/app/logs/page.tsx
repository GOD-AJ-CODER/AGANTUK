"use client";

import React, { useState, useEffect } from "react";
import {
  FileText,
  ShieldCheck,
  ShieldAlert,
  Search,
  Filter,
  Hash,
  RefreshCw,
  Clock,
  ExternalLink,
} from "lucide-react";
import { VerdictStatus } from "../../lib/types";

interface AuditRecordItem {
  log_id: string;
  timestamp_utc: string;
  officer_id: string;
  doc_type?: string | null;
  doc_number?: string | null;
  verdict: VerdictStatus;
  failure_codes?: string[];
  audit_hash?: string | null;
  is_valid_hash?: boolean;
}

export default function LogsPage() {
  const [records, setRecords] = useState<AuditRecordItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedVerdict, setSelectedVerdict] = useState<string>("ALL");

  const loadLogs = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/logs");
      if (res.ok) {
        const data = await res.json();
        setRecords(data.records || []);
      }
    } catch (err) {
      console.error("Failed to load audit logs:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, []);

  const filteredRecords = records.filter((r) => {
    const matchesVerdict =
      selectedVerdict === "ALL" || r.verdict === selectedVerdict;
    const query = searchQuery.toLowerCase().trim();
    const matchesQuery =
      !query ||
      (r.doc_number && r.doc_number.toLowerCase().includes(query)) ||
      (r.officer_id && r.officer_id.toLowerCase().includes(query)) ||
      (r.log_id && r.log_id.toLowerCase().includes(query)) ||
      (r.audit_hash && r.audit_hash.toLowerCase().includes(query));
    return matchesVerdict && matchesQuery;
  });

  const getVerdictBadge = (verdict: VerdictStatus) => {
    switch (verdict) {
      case "PASS":
        return (
          <span className="bg-[#00E676]/20 border-2 border-[#00E676] text-[#00E676] px-2.5 py-1 font-mono font-bold text-xs uppercase">
            [ ✓ ] PASS
          </span>
        );
      case "MANUAL_REVIEW":
        return (
          <span className="bg-[#FFC107]/20 border-2 border-[#FFC107] text-[#FFC107] px-2.5 py-1 font-mono font-bold text-xs uppercase">
            [ ! ] MANUAL REVIEW
          </span>
        );
      case "FLAGGED":
        return (
          <span className="bg-[#FF3B30]/20 border-2 border-[#FF3B30] text-[#FF3B30] px-2.5 py-1 font-mono font-bold text-xs uppercase">
            [ X ] FLAGGED
          </span>
        );
      case "CRITICAL_SECURITY_ALERT":
        return (
          <span className="bg-[#FF3B30] text-black px-2.5 py-1 font-mono font-black text-xs uppercase animate-pulse">
            [ ⛔ ] ALERT
          </span>
        );
      default:
        return <span className="text-white font-mono text-xs">{verdict}</span>;
    }
  };

  return (
    <div className="w-full flex flex-col gap-6">
      {/* Header & Stats Banner */}
      <div className="bg-white border border-[#CBD5E1] rounded-xl p-6 shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 border border-[#CBD5E1] bg-[#F8FAFC] rounded-lg flex items-center justify-center">
            <FileText className="w-6 h-6 text-[#0284C7]" />
          </div>
          <div>
            <h1 className="text-2xl font-bold uppercase tracking-wider text-[#0F172A]">
              Immutable Non-Repudiation Audit Trail
            </h1>
            <p className="text-xs font-mono text-[#64748B]">
              RULE 7.1 COMPLIANCE: WRITE-BEFORE-RESPOND SHA-256 VERIFIED RECORDS
            </p>
          </div>
        </div>

        <button
          onClick={loadLogs}
          disabled={loading}
          className="touch-target-sm px-4 border border-[#CBD5E1] bg-white hover:bg-[#F8FAFC] text-[#0F172A] rounded-lg flex items-center gap-2 cursor-pointer font-bold text-xs uppercase shadow-sm transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin text-[#0284C7]" : ""}`} />
          <span>Refresh Trail</span>
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Search */}
        <div className="md:col-span-2 relative">
          <input
            type="text"
            placeholder="Search by Document Number, Officer ID, Log UUID, or SHA-256 Hash..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-white border border-[#CBD5E1] rounded-lg p-3 pl-10 text-[#0F172A] font-mono text-sm focus:border-[#0284C7] outline-none touch-target-sm shadow-sm"
          />
          <Search className="w-4 h-4 text-[#64748B] absolute left-3.5 top-4" />
        </div>

        {/* Verdict Filter */}
        <div className="relative">
          <select
            value={selectedVerdict}
            onChange={(e) => setSelectedVerdict(e.target.value)}
            className="w-full bg-white border border-[#CBD5E1] rounded-lg p-3 text-[#0F172A] font-mono text-sm focus:border-[#0284C7] outline-none touch-target-sm cursor-pointer shadow-sm"
          >
            <option value="ALL">ALL VERDICTS ({records.length})</option>
            <option value="PASS">PASS ONLY</option>
            <option value="MANUAL_REVIEW">MANUAL REVIEW ONLY</option>
            <option value="FLAGGED">FLAGGED ONLY</option>
            <option value="CRITICAL_SECURITY_ALERT">CRITICAL SECURITY ALERT ONLY</option>
          </select>
        </div>
      </div>

      {/* Audit Log Table */}
      <div className="w-full bg-white border border-[#CBD5E1] rounded-xl overflow-hidden shadow-sm">
        <table className="w-full text-left border-collapse font-mono text-xs">
          <thead>
            <tr className="bg-[#0F172A] border-b border-[#0F172A] text-white uppercase">
              <th className="p-3.5 font-bold">Timestamp (UTC)</th>
              <th className="p-3.5 font-bold">Verdict</th>
              <th className="p-3.5 font-bold">Document No.</th>
              <th className="p-3.5 font-bold">Officer ID</th>
              <th className="p-3.5 font-bold">Failure Codes</th>
              <th className="p-3.5 font-bold">SHA-256 Cryptographic Hash</th>
              <th className="p-3.5 font-bold text-center">Integrity</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E2E8F0]">
            {filteredRecords.length === 0 ? (
              <tr>
                <td colSpan={7} className="p-8 text-center text-[#64748B]">
                  {loading
                    ? "LOADING SECURE AUDIT TRAIL FROM DISK..."
                    : "NO AUDIT RECORDS FOUND MATCHING ACTIVE FILTER CRITERIA."}
                </td>
              </tr>
            ) : (
              filteredRecords.map((r) => (
                <tr key={r.log_id} className="hover:bg-[#F8FAFC] transition-colors">
                  <td className="p-3.5 whitespace-nowrap text-[#0F172A]">
                    <div className="flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5 text-[#64748B]" />
                      <span>{r.timestamp_utc || "—"}</span>
                    </div>
                  </td>

                  <td className="p-3.5 whitespace-nowrap">{getVerdictBadge(r.verdict)}</td>

                  <td className="p-3.5 font-bold text-[#0284C7] whitespace-nowrap">
                    {r.doc_number || "—"}
                  </td>

                  <td className="p-3.5 text-[#0F172A] whitespace-nowrap">{r.officer_id}</td>

                  <td className="p-3.5 max-w-xs truncate text-[#DC2626]">
                    {r.failure_codes && r.failure_codes.length > 0
                      ? r.failure_codes.join(", ")
                      : "CLEAN"}
                  </td>

                  <td className="p-3.5 font-mono text-[11px] text-[#64748B] max-w-sm break-all select-all">
                    {r.audit_hash ? (
                      <span className="text-[#0F172A] hover:text-[#0284C7]">{r.audit_hash}</span>
                    ) : (
                      "UNHASHED LEGACY"
                    )}
                  </td>

                  <td className="p-3.5 text-center whitespace-nowrap">
                    {r.is_valid_hash !== false ? (
                      <span className="inline-flex items-center gap-1 text-[#16A34A] font-bold text-[11px]">
                        <ShieldCheck className="w-4 h-4 text-[#16A34A]" /> VERIFIED
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[#DC2626] font-bold text-[11px] bg-[#FEE2E2] px-2 py-0.5 border border-[#EF4444] rounded">
                        <ShieldAlert className="w-4 h-4 text-[#DC2626]" /> TAMPERED
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
