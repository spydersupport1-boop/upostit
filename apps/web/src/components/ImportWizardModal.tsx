"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { importApi, ImportJobDto, ApiError } from "@/lib/api";

export interface ImportWizardModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string | null;
  onImportCompleted?: () => void;
}

export default function ImportWizardModal({
  isOpen,
  onClose,
  token,
  onImportCompleted,
}: ImportWizardModalProps) {
  // Wizard Step: 1 to 7
  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5 | 6 | 7>(1);

  // File States
  const [file, setFile] = useState<File | null>(null);
  const [filePreviewRows, setFilePreviewRows] = useState<string[][]>([]);
  const [fileHeaders, setFileHeaders] = useState<string[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);

  // Download / Upload States
  const [isDownloadingTemplate, setIsDownloadingTemplate] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  // Job & Progress States
  const [job, setJob] = useState<ImportJobDto | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const [isDownloadingErrors, setIsDownloadingErrors] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Reset state on open/close
  useEffect(() => {
    if (isOpen) {
      setStep(1);
      setFile(null);
      setFilePreviewRows([]);
      setFileHeaders([]);
      setFileError(null);
      setJob(null);
    } else {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    }
  }, [isOpen]);

  // Clean up poll interval on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  // Helper to trigger browser download from a blob
  const triggerBlobDownload = (blob: Blob, filename: string) => {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  // Download Template Handler
  const handleDownloadTemplate = async (format: "csv" | "xlsx") => {
    if (!token) return;
    setIsDownloadingTemplate(format);
    setFileError(null);
    try {
      const blob = await importApi.downloadTemplate(format, token);
      triggerBlobDownload(blob, `employee_import_template.${format}`);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setFileError(`Failed to download template: ${err.detail}`);
      } else {
        setFileError("Failed to download template file.");
      }
    } finally {
      setIsDownloadingTemplate(null);
    }
  };

  // File Selection Handler
  const handleFileSelected = (selectedFile: File) => {
    setFileError(null);

    // Validate size (max 10 MB matching backend MAX_IMPORT_FILE_SIZE)
    const MAX_SIZE = 10 * 1024 * 1024;
    if (selectedFile.size > MAX_SIZE) {
      setFileError("File exceeds the maximum 10 MB upload limit.");
      return;
    }

    // Validate extension
    const ext = selectedFile.name.split(".").pop()?.toLowerCase();
    if (ext !== "csv" && ext !== "xlsx") {
      setFileError("Invalid format. Only .csv and .xlsx files are supported.");
      return;
    }

    setFile(selectedFile);

    // If CSV, parse first 6 lines client-side for immediate preview
    if (ext === "csv") {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target?.result as string;
        if (text) {
          const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
          if (lines.length > 0) {
            const rawHeaders = lines[0].split(",").map((h) => h.trim().replace(/^["']|["']$/g, ""));
            setFileHeaders(rawHeaders);
            const preview = lines.slice(1, 6).map((line) =>
              line.split(",").map((c) => c.trim().replace(/^["']|["']$/g, ""))
            );
            setFilePreviewRows(preview);
          }
        }
      };
      reader.readAsText(selectedFile.slice(0, 8192)); // Read first 8KB
    } else {
      setFileHeaders(["Excel Sheet"]);
      setFilePreviewRows([]);
    }

    setStep(3); // Proceed to preview
  };

  // Poll Import Job Progress
  const startPollingJob = useCallback((jobId: string) => {
    if (!token) return;
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
    }
    const interval = setInterval(async () => {
      try {
        const currentJob = await importApi.getJobStatus(jobId, token);
        setJob(currentJob);

        if (currentJob.status === "completed" || currentJob.status === "failed") {
          clearInterval(interval);
          pollIntervalRef.current = null;
          setStep(7); // Show final summary
          if (onImportCompleted) {
            onImportCompleted();
          }
        }
      } catch {
        // keep polling or handled on final timeout
      }
    }, 1500);

    pollIntervalRef.current = interval;
  }, [token, onImportCompleted]);

  // Upload and Submit Import
  const handleConfirmImport = async () => {
    if (!file || !token) return;
    setIsUploading(true);
    setFileError(null);
    setStep(6); // Transition to progress

    try {
      const createdJob = await importApi.uploadFile(file, token);
      setJob(createdJob);
      startPollingJob(createdJob.id);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setFileError(err.detail);
      } else {
        setFileError("Failed to upload and initiate import job.");
      }
      setStep(4); // Back to error view
    } finally {
      setIsUploading(false);
    }
  };

  // Download Error CSV Report
  const handleDownloadErrors = async () => {
    if (!job || !token) return;
    setIsDownloadingErrors(true);
    try {
      const blob = await importApi.downloadErrorReport(job.id, token);
      triggerBlobDownload(blob, `import_errors_${job.id}.csv`);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setFileError(err.detail);
      } else {
        setFileError("Failed to download error report.");
      }
    } finally {
      setIsDownloadingErrors(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        style={{ maxWidth: "760px", padding: "2.25rem" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header & Stepper */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
              <span style={{ fontSize: "1.25rem" }}>📥</span>
              <h2 className="modal-title" style={{ margin: 0 }}>Bulk Employee Import Wizard</h2>
            </div>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.825rem", margin: 0 }}>
              Batch onboard workforces with automated validation, rollback protection, and failure reports.
            </p>
          </div>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        {/* 7-Step Progress Stepper Indicator */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "2rem", background: "rgba(0,0,0,0.3)", padding: "0.75rem 1rem", borderRadius: "10px", border: "1px solid var(--border-color)" }}>
          {[
            { s: 1, label: "Template" },
            { s: 2, label: "Upload" },
            { s: 3, label: "Preview" },
            { s: 4, label: "Validate" },
            { s: 5, label: "Confirm" },
            { s: 6, label: "Process" },
            { s: 7, label: "Summary" },
          ].map(({ s, label }, idx, arr) => (
            <React.Fragment key={s}>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <div
                  style={{
                    width: "24px",
                    height: "24px",
                    borderRadius: "50%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    background:
                      step === s
                        ? "linear-gradient(135deg, var(--accent-cyan), var(--accent-blue))"
                        : step > s
                        ? "#10b981"
                        : "rgba(255, 255, 255, 0.08)",
                    color: step >= s ? "#fff" : "var(--text-muted)",
                    boxShadow: step === s ? "0 0 10px rgba(6, 182, 212, 0.5)" : "none",
                  }}
                >
                  {step > s ? "✓" : s}
                </div>
                <span
                  style={{
                    fontSize: "0.75rem",
                    fontWeight: step === s ? 700 : 500,
                    color: step === s ? "var(--text-primary)" : "var(--text-muted)",
                    display: "inline-block",
                  }}
                >
                  {label}
                </span>
              </div>
              {idx < arr.length - 1 && (
                <div
                  style={{
                    flex: 1,
                    height: "2px",
                    background: step > s ? "#10b981" : "rgba(255, 255, 255, 0.08)",
                    margin: "0 6px",
                  }}
                />
              )}
            </React.Fragment>
          ))}
        </div>

        {fileError && (
          <div className="alert alert-danger" style={{ marginBottom: "1.5rem" }}>
            <span>{fileError}</span>
            <button className="alert-close" onClick={() => setFileError(null)}>&times;</button>
          </div>
        )}

        {/* =====================================================================
            STEP 1: DOWNLOAD TEMPLATE
            ===================================================================== */}
        {step === 1 && (
          <div>
            <div className="card" style={{ padding: "1.75rem", marginBottom: "1.75rem", background: "rgba(0,0,0,0.25)" }}>
              <h3 style={{ fontSize: "1.05rem", fontWeight: 700, marginBottom: "0.75rem" }}>
                Step 1: Download Standard Onboarding Template
              </h3>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: "1.6", marginBottom: "1.25rem" }}>
                Use our pre-configured templates to format your employee directory. Required columns: <code>employee_id</code>, <code>first_name</code>, <code>last_name</code>, <code>work_email</code>, <code>joining_date</code>, <code>employment_type</code>. Optional columns: <code>department_code</code>, <code>designation_code</code>, <code>phone_number</code>, <code>work_location</code>, <code>primary_workplace_code</code>.
              </p>

              <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={isDownloadingTemplate === "csv"}
                  onClick={() => handleDownloadTemplate("csv")}
                >
                  {isDownloadingTemplate === "csv" ? "Downloading..." : "📄 Download CSV Template"}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={isDownloadingTemplate === "xlsx"}
                  onClick={() => handleDownloadTemplate("xlsx")}
                >
                  {isDownloadingTemplate === "xlsx" ? "Downloading..." : "📊 Download Excel (XLSX) Template"}
                </button>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button type="button" className="btn btn-primary" onClick={() => setStep(2)}>
                Next: Upload Completed File →
              </button>
            </div>
          </div>
        )}

        {/* =====================================================================
            STEP 2: UPLOAD CSV / XLSX FILE
            ===================================================================== */}
        {step === 2 && (
          <div>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 700, marginBottom: "0.75rem" }}>
              Step 2: Upload CSV or XLSX Roster
            </h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1.5rem" }}>
              Upload your completed spreadsheet. Max limit: <strong>2,000 rows</strong> and <strong>10 MB file size</strong>.
            </p>

            <div
              style={{
                border: "2px dashed var(--border-color)",
                borderRadius: "12px",
                padding: "3rem 2rem",
                textAlign: "center",
                background: "rgba(0,0,0,0.2)",
                cursor: "pointer",
                transition: "border-color 0.2s ease",
                marginBottom: "1.75rem",
              }}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                  handleFileSelected(e.dataTransfer.files[0]);
                }
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv, .xlsx"
                style={{ display: "none" }}
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    handleFileSelected(e.target.files[0]);
                  }
                }}
              />
              <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>📁</div>
              <h4 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "0.5rem" }}>
                Click to select or drag and drop file here
              </h4>
              <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
                Supported formats: CSV, XLSX (Up to 10 MB)
              </p>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <button type="button" className="btn btn-secondary" onClick={() => setStep(1)}>
                ← Back
              </button>
            </div>
          </div>
        )}

        {/* =====================================================================
            STEP 3: PREVIEW & VALIDATE DATA
            ===================================================================== */}
        {step === 3 && file && (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <div>
                <h3 style={{ fontSize: "1.05rem", fontWeight: 700 }}>Step 3: Preview Data Sample</h3>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                  File: <strong style={{ color: "var(--text-primary)" }}>{file.name}</strong> ({(file.size / 1024).toFixed(1)} KB)
                </p>
              </div>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setFile(null);
                  setStep(2);
                }}
              >
                Change File
              </button>
            </div>

            {filePreviewRows.length > 0 ? (
              <div className="table-container" style={{ maxHeight: "240px", overflowY: "auto", marginBottom: "1.5rem" }}>
                <table className="data-table" style={{ fontSize: "0.8rem" }}>
                  <thead>
                    <tr>
                      {fileHeaders.slice(0, 7).map((h, i) => (
                        <th key={i}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filePreviewRows.map((row, rIdx) => (
                      <tr key={rIdx}>
                        {row.slice(0, 7).map((cell, cIdx) => (
                          <td key={cIdx}>{cell || "—"}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="card" style={{ padding: "1.5rem", marginBottom: "1.5rem", background: "rgba(0,0,0,0.2)" }}>
                <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                  Excel workbook loaded. Full row structure and column validations will be evaluated server-side.
                </p>
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <button type="button" className="btn btn-secondary" onClick={() => setStep(2)}>
                ← Back
              </button>
              <button type="button" className="btn btn-primary" onClick={() => setStep(4)}>
                Next: Pre-Validation Check →
              </button>
            </div>
          </div>
        )}

        {/* =====================================================================
            STEP 4: ROW-LEVEL ERROR CHECK / PRE-VALIDATION
            ===================================================================== */}
        {step === 4 && (
          <div>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 700, marginBottom: "0.75rem" }}>
              Step 4: Pre-Validation & Integrity Checks
            </h3>
            <div className="card" style={{ padding: "1.5rem", marginBottom: "1.5rem", background: "rgba(0,0,0,0.2)" }}>
              <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: "0.875rem", lineHeight: "1.8" }}>
                <li style={{ color: "#34d399" }}>✓ File size ({((file?.size || 0) / 1024).toFixed(1)} KB) is within 10 MB limit.</li>
                <li style={{ color: "#34d399" }}>✓ Valid extension ({file?.name.split(".").pop()?.toUpperCase()}) detected.</li>
                <li style={{ color: "var(--text-secondary)" }}>
                  ℹ Automatic Chunk Rollback: If any row fails within a 100-row batch, only that failed record is marked while valid rows are saved.
                </li>
                <li style={{ color: "var(--text-secondary)" }}>
                  ℹ Multi-Tenancy Isolation: All departmental, designation, and primary location codes will be resolved strictly within your tenant.
                </li>
              </ul>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <button type="button" className="btn btn-secondary" onClick={() => setStep(3)}>
                ← Back
              </button>
              <button type="button" className="btn btn-primary" onClick={() => setStep(5)}>
                Next: Confirm & Queue Import →
              </button>
            </div>
          </div>
        )}

        {/* =====================================================================
            STEP 5: CONFIRM IMPORT
            ===================================================================== */}
        {step === 5 && (
          <div>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 700, marginBottom: "0.75rem" }}>
              Step 5: Confirm Asynchronous Import
            </h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1.5rem" }}>
              Please confirm the dispatch of the asynchronous Celery processing pipeline.
            </p>

            <div className="card" style={{ padding: "1.5rem", marginBottom: "1.75rem", background: "rgba(0,0,0,0.25)" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", fontSize: "0.875rem" }}>
                <div>
                  <div style={{ color: "var(--text-muted)", fontSize: "0.775rem" }}>Target File</div>
                  <strong style={{ color: "var(--text-primary)" }}>{file?.name}</strong>
                </div>
                <div>
                  <div style={{ color: "var(--text-muted)", fontSize: "0.775rem" }}>File Size</div>
                  <strong style={{ color: "var(--text-primary)" }}>{((file?.size || 0) / 1024).toFixed(1)} KB</strong>
                </div>
                <div>
                  <div style={{ color: "var(--text-muted)", fontSize: "0.775rem" }}>Storage Engine</div>
                  <strong style={{ color: "var(--accent-cyan)" }}>Tenant S3/MinIO Encrypted Bucket</strong>
                </div>
                <div>
                  <div style={{ color: "var(--text-muted)", fontSize: "0.775rem" }}>Execution Engine</div>
                  <strong style={{ color: "var(--accent-cyan)" }}>Celery Distributed Workers</strong>
                </div>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <button type="button" className="btn btn-secondary" onClick={() => setStep(4)}>
                ← Back
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={isUploading}
                onClick={handleConfirmImport}
              >
                {isUploading ? "Uploading & Dispatching..." : "🚀 Launch Import Task"}
              </button>
            </div>
          </div>
        )}

        {/* =====================================================================
            STEP 6: PROCESSING PROGRESS
            ===================================================================== */}
        {step === 6 && (
          <div style={{ textAlign: "center", padding: "2rem 1rem" }}>
            <div className="spinner" style={{ margin: "0 auto 1.5rem" }} />
            <h3 style={{ fontSize: "1.2rem", fontWeight: 700, marginBottom: "0.5rem" }}>
              Import Pipeline Running...
            </h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1.75rem" }}>
              Job ID: <code>{job?.id || "Initiating..."}</code>
            </p>

            {/* Live Progress Bar */}
            <div style={{ width: "100%", height: "10px", background: "rgba(255,255,255,0.08)", borderRadius: "5px", overflow: "hidden", marginBottom: "1rem" }}>
              <div
                style={{
                  height: "100%",
                  background: "linear-gradient(90deg, var(--accent-cyan), var(--accent-blue))",
                  width: `${job && job.total_rows > 0 ? Math.min(100, Math.round((job.processed_rows / job.total_rows) * 100)) : 10}%`,
                  transition: "width 0.4s ease",
                }}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.825rem", color: "var(--text-muted)" }}>
              <span>Status: <strong style={{ color: "var(--accent-cyan)", textTransform: "capitalize" }}>{job?.status || "queued"}</strong></span>
              <span>
                Processed: <strong>{job?.processed_rows || 0}</strong> / {job?.total_rows || "calculating..."}
              </span>
            </div>
          </div>
        )}

        {/* =====================================================================
            STEP 7: SUCCESS / FAILURE SUMMARY & ERROR REPORT
            ===================================================================== */}
        {step === 7 && job && (
          <div>
            <div style={{ textAlign: "center", marginBottom: "1.5rem" }}>
              <div
                style={{
                  width: "56px",
                  height: "56px",
                  borderRadius: "50%",
                  background: job.failed_rows === 0 ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)",
                  color: job.failed_rows === 0 ? "#10b981" : "#f59e0b",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "1.75rem",
                  margin: "0 auto 1rem",
                }}
              >
                {job.failed_rows === 0 ? "✓" : "!"}
              </div>
              <h3 style={{ fontSize: "1.3rem", fontWeight: 800 }}>
                {job.failed_rows === 0 ? "Import Completed Successfully!" : "Import Completed with Warnings"}
              </h3>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                Job {job.id} completed. Check the summary below for results.
              </p>
            </div>

            {/* Counters Grid */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1rem", marginBottom: "1.75rem" }}>
              <div className="card" style={{ padding: "1.25rem", textAlign: "center", background: "rgba(0,0,0,0.2)" }}>
                <div style={{ fontSize: "1.5rem", fontWeight: 800, color: "var(--text-primary)" }}>{job.total_rows}</div>
                <div style={{ fontSize: "0.775rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>Total Rows</div>
              </div>
              <div className="card" style={{ padding: "1.25rem", textAlign: "center", background: "rgba(16, 185, 129, 0.08)", border: "1px solid rgba(16, 185, 129, 0.2)" }}>
                <div style={{ fontSize: "1.5rem", fontWeight: 800, color: "#34d399" }}>{job.succeeded_rows}</div>
                <div style={{ fontSize: "0.775rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>Successfully Imported</div>
              </div>
              <div className="card" style={{ padding: "1.25rem", textAlign: "center", background: job.failed_rows > 0 ? "rgba(239, 68, 68, 0.08)" : "rgba(0,0,0,0.2)", border: job.failed_rows > 0 ? "1px solid rgba(239, 68, 68, 0.2)" : "1px solid var(--border-color)" }}>
                <div style={{ fontSize: "1.5rem", fontWeight: 800, color: job.failed_rows > 0 ? "#f87171" : "var(--text-muted)" }}>{job.failed_rows}</div>
                <div style={{ fontSize: "0.775rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>Failed Records</div>
              </div>
            </div>

            {/* Error Diagnostics List if any */}
            {job.failed_rows > 0 && job.error_summary && job.error_summary.length > 0 && (
              <div style={{ marginBottom: "1.75rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                  <h4 style={{ fontSize: "0.9rem", fontWeight: 700, color: "#f87171" }}>
                    Row Diagnostics ({job.error_summary.length} items logged)
                  </h4>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={isDownloadingErrors}
                    onClick={handleDownloadErrors}
                  >
                    {isDownloadingErrors ? "Downloading..." : "📥 Download Error Report (CSV)"}
                  </button>
                </div>
                <div style={{ maxHeight: "160px", overflowY: "auto", background: "rgba(0,0,0,0.3)", borderRadius: "8px", padding: "0.75rem", border: "1px solid var(--border-color)", fontSize: "0.8rem" }}>
                  {job.error_summary.slice(0, 20).map((err, i) => (
                    <div key={i} style={{ padding: "0.4rem 0", borderBottom: "1px solid rgba(255,255,255,0.04)", color: "#fca5a5" }}>
                      <strong>Row {err.row_number}:</strong> {err.errors.join("; ")}
                    </div>
                  ))}
                  {job.error_summary.length > 20 && (
                    <div style={{ padding: "0.5rem 0", color: "var(--text-muted)", fontStyle: "italic", textAlign: "center" }}>
                      ... and {job.error_summary.length - 20} more rows. Download the full CSV error report above.
                    </div>
                  )}
                </div>
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => {
                  onClose();
                  if (onImportCompleted) onImportCompleted();
                }}
              >
                Done & Refresh Directory
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
