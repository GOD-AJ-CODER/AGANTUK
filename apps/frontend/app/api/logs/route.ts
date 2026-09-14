import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import crypto from "crypto";

export async function GET() {
  // Read from database/audit_trail.jsonl
  const projectRoot = path.resolve(process.cwd(), "..", "..");
  const jsonlPath = path.join(projectRoot, "database", "audit_trail.jsonl");

  const records: any[] = [];

  if (fs.existsSync(jsonlPath)) {
    try {
      const fileContent = fs.readFileSync(jsonlPath, "utf-8");
      const lines = fileContent.split("\n");

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const item = JSON.parse(trimmed);

          // Canonical verification
          const canonical = {
            doc_number: item.doc_number != null ? String(item.doc_number) : null,
            doc_type: item.doc_type != null ? String(item.doc_type) : null,
            failure_codes: Array.isArray(item.failure_codes)
              ? item.failure_codes.map(String).sort()
              : [],
            forensics_metrics: item.forensics_metrics || {},
            log_id: String(item.log_id || ""),
            officer_id: String(item.officer_id || ""),
            raw_mrz: Array.isArray(item.raw_mrz) ? item.raw_mrz.map(String) : [],
            timestamp_utc: String(item.timestamp_utc || ""),
            verdict: String(item.verdict || ""),
          };

          const canonicalJson = JSON.stringify(canonical);
          const computedHash = crypto.createHash("sha256").update(canonicalJson).digest("hex");
          const isValid = (item.audit_hash || "").toLowerCase() === computedHash.toLowerCase();

          records.push({
            ...item,
            is_valid_hash: isValid,
          });
        } catch {
          // ignore corrupted lines
        }
      }
    } catch (e) {
      console.error("Failed to read audit_trail.jsonl:", e);
    }
  }

  // Reverse to get newest first
  records.reverse();

  return NextResponse.json({
    total: records.length,
    records,
  });
}
