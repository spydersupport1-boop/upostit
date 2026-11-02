"use client";

import React, { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  invitationApi,
  ValidateInvitationResponseDto,
  ApiError,
} from "@/lib/api";

function ActivateAccountContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  // Validation States
  const [isValidating, setIsValidating] = useState(true);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [invitationData, setInvitationData] = useState<ValidateInvitationResponseDto | null>(null);

  // Form States
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isActivated, setIsActivated] = useState(false);

  // Validate token on mount
  useEffect(() => {
    if (!token) {
      setIsValidating(false);
      setValidationError("No activation token was provided in the invitation link. Please verify the URL or contact your company administrator.");
      return;
    }

    let isMounted = true;
    async function validate() {
      setIsValidating(true);
      setValidationError(null);
      try {
        const data = await invitationApi.validateToken(token);
        if (isMounted) {
          if (data.valid) {
            setInvitationData(data);
          } else {
            setValidationError("This invitation token is invalid, has expired, or has already been accepted.");
          }
        }
      } catch (err: unknown) {
        if (isMounted) {
          if (err instanceof ApiError) {
            setValidationError(err.detail);
          } else {
            setValidationError("Unable to validate the invitation link. Please check your internet connection and try again.");
          }
        }
      } finally {
        if (isMounted) {
          setIsValidating(false);
        }
      }
    }

    validate();
    return () => {
      isMounted = false;
    };
  }, [token]);

  // Password Strength Calculation
  const hasMinLength = password.length >= 8;
  const hasUppercase = /[A-Z]/.test(password);
  const hasLowercase = /[a-z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  const hasSpecial = /[^A-Za-z0-9]/.test(password);
  const passwordsMatch = password.length > 0 && password === passwordConfirm;

  const strengthScore = [hasMinLength, hasUppercase, hasLowercase, hasNumber, hasSpecial].filter(Boolean).length;
  const isPasswordValid = hasMinLength && (hasUppercase || hasLowercase) && passwordsMatch;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);

    if (!hasMinLength) {
      setSubmitError("Password must be at least 8 characters long.");
      return;
    }

    if (!passwordsMatch) {
      setSubmitError("Password and confirmation password do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      await invitationApi.activateAccount({
        token,
        password,
        password_confirm: passwordConfirm,
      });
      setIsActivated(true);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setSubmitError(err.detail);
      } else {
        setSubmitError("Failed to activate account. The invitation may have expired or reached maximum attempt limits.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="container" style={{ minHeight: "85vh", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center" }}>
      {/* Top Brand Banner */}
      <div style={{ textAlign: "center", marginBottom: "2rem" }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
          <div className="logo-dot" />
          <span style={{ fontSize: "1.35rem", fontWeight: 800, letterSpacing: "-0.02em" }}>Attendance SaaS</span>
          <span className="badge">Security Activation</span>
        </div>
        <h1 style={{ fontSize: "2rem", fontWeight: 800, letterSpacing: "-0.02em" }}>
          Activate Your Employee Account
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", maxWidth: "480px", margin: "0.5rem auto 0" }}>
          Establish your secure login credentials to access your company&apos;s workspace and geofenced attendance system.
        </p>
      </div>

      {/* Main Card */}
      <div className="card" style={{ width: "100%", maxWidth: "520px", padding: "2.5rem", boxShadow: "0 20px 45px rgba(0,0,0,0.5)" }}>
        {/* Loading State */}
        {isValidating && (
          <div className="spinner-container" style={{ padding: "3rem 1rem", textAlign: "center" }}>
            <div className="spinner" style={{ margin: "0 auto 1.5rem" }} />
            <h2 style={{ fontSize: "1.1rem", fontWeight: 700 }}>Cryptographically Validating Invitation...</h2>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: "0.5rem" }}>
              Verifying token hash against tenant multi-tenancy registry.
            </p>
          </div>
        )}

        {/* Validation Error State */}
        {!isValidating && validationError && (
          <div style={{ textAlign: "center", padding: "1.5rem 0" }}>
            <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>⚠️</div>
            <h2 style={{ fontSize: "1.3rem", fontWeight: 700, color: "#f87171", marginBottom: "0.75rem" }}>
              Invalid or Expired Invitation
            </h2>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", lineHeight: "1.6", marginBottom: "2rem" }}>
              {validationError}
            </p>
            <div style={{ display: "flex", gap: "1rem", justifyContent: "center" }}>
              <Link href="/organization" className="btn btn-secondary">
                Return to Workspace
              </Link>
            </div>
          </div>
        )}

        {/* Activation Success State */}
        {!isValidating && isActivated && (
          <div style={{ textAlign: "center", padding: "1.5rem 0" }}>
            <div
              style={{
                width: "64px",
                height: "64px",
                borderRadius: "50%",
                background: "rgba(16, 185, 129, 0.15)",
                color: "#10b981",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "2rem",
                margin: "0 auto 1.5rem",
                border: "2px solid rgba(16, 185, 129, 0.4)",
              }}
            >
              ✓
            </div>
            <h2 style={{ fontSize: "1.4rem", fontWeight: 800, color: "#34d399", marginBottom: "0.5rem" }}>
              Account Successfully Activated!
            </h2>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", lineHeight: "1.6", marginBottom: "1.75rem" }}>
              Your login credentials have been securely provisioned with Argon2id password hashing. You can now sign in to your company&apos;s workspace.
            </p>
            <div style={{ background: "rgba(0,0,0,0.3)", borderRadius: "8px", padding: "1rem", marginBottom: "2rem", textAlign: "left", border: "1px solid var(--border-color)" }}>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.25rem" }}>Company Workspace</div>
              <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{invitationData?.company_name}</div>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.75rem", marginBottom: "0.25rem" }}>Sign-In Email</div>
              <div style={{ fontWeight: 600, color: "var(--accent-cyan)" }}>{invitationData?.email}</div>
            </div>
            <Link href="/organization" className="btn btn-primary" style={{ width: "100%", padding: "0.75rem 1rem", fontSize: "1rem" }}>
              Proceed to Sign In →
            </Link>
          </div>
        )}

        {/* Valid Activation Form */}
        {!isValidating && !validationError && !isActivated && invitationData && (
          <div>
            {/* Invitee Metadata Card */}
            <div style={{ background: "rgba(0,0,0,0.25)", borderRadius: "10px", padding: "1rem 1.25rem", marginBottom: "1.75rem", border: "1px solid var(--border-color)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>
                  Organization
                </span>
                <span className="badge badge-green" style={{ fontSize: "0.75rem" }}>Verified Invite</span>
              </div>
              <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)" }}>{invitationData.company_name}</div>
              <div style={{ display: "flex", gap: "1rem", marginTop: "0.75rem", fontSize: "0.85rem", color: "var(--text-secondary)", borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "0.5rem" }}>
                <div>Employee: <strong style={{ color: "var(--text-primary)" }}>{invitationData.employee_name}</strong></div>
                <div>Email: <strong style={{ color: "var(--accent-cyan)" }}>{invitationData.email}</strong></div>
              </div>
            </div>

            {submitError && (
              <div className="alert alert-danger" style={{ marginBottom: "1.5rem" }}>
                <span>{submitError}</span>
              </div>
            )}

            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
                  <label className="form-label" style={{ margin: 0 }}>Create New Password</label>
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    style={{ background: "none", border: "none", color: "var(--accent-cyan)", fontSize: "0.8rem", cursor: "pointer" }}
                  >
                    {showPassword ? "Hide" : "Show"}
                  </button>
                </div>
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  autoComplete="new-password"
                  placeholder="Minimum 8 characters"
                  className="form-control"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              {/* Password Strength Indicator */}
              <div style={{ marginBottom: "1.25rem" }}>
                <div style={{ display: "flex", gap: "4px", marginBottom: "6px" }}>
                  {[1, 2, 3, 4, 5].map((level) => (
                    <div
                      key={level}
                      style={{
                        flex: 1,
                        height: "4px",
                        borderRadius: "2px",
                        background:
                          level <= strengthScore
                            ? strengthScore <= 2
                              ? "#ef4444"
                              : strengthScore <= 3
                              ? "#f59e0b"
                              : "#10b981"
                            : "rgba(255, 255, 255, 0.1)",
                        transition: "background 0.2s ease",
                      }}
                    />
                  ))}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                  <span style={{ color: hasMinLength ? "#10b981" : "var(--text-muted)" }}>
                    {hasMinLength ? "✓" : "○"} 8+ characters
                  </span>
                  <span style={{ color: hasUppercase ? "#10b981" : "var(--text-muted)" }}>
                    {hasUppercase ? "✓" : "○"} Uppercase letter
                  </span>
                  <span style={{ color: hasLowercase ? "#10b981" : "var(--text-muted)" }}>
                    {hasLowercase ? "✓" : "○"} Lowercase letter
                  </span>
                  <span style={{ color: hasNumber || hasSpecial ? "#10b981" : "var(--text-muted)" }}>
                    {hasNumber || hasSpecial ? "✓" : "○"} Number or symbol
                  </span>
                </div>
              </div>

              <div className="form-group" style={{ marginBottom: "1.75rem" }}>
                <label className="form-label">Confirm Password</label>
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  autoComplete="new-password"
                  placeholder="Re-enter your password"
                  className="form-control"
                  value={passwordConfirm}
                  onChange={(e) => setPasswordConfirm(e.target.value)}
                />
                {passwordConfirm && !passwordsMatch && (
                  <div style={{ fontSize: "0.775rem", color: "#f87171", marginTop: "0.35rem" }}>
                    Passwords do not match
                  </div>
                )}
                {passwordsMatch && (
                  <div style={{ fontSize: "0.775rem", color: "#34d399", marginTop: "0.35rem" }}>
                    ✓ Passwords match
                  </div>
                )}
              </div>

              <button
                type="submit"
                disabled={isSubmitting || !isPasswordValid}
                className="btn btn-primary"
                style={{ width: "100%", padding: "0.75rem 1rem", fontSize: "0.95rem" }}
              >
                {isSubmitting ? (
                  <>
                    <span className="spinner spinner-sm" />
                    Activating Account...
                  </>
                ) : (
                  "Activate Account & Establish Password"
                )}
              </button>
            </form>
          </div>
        )}
      </div>

      <footer className="footer" style={{ marginTop: "2rem", textAlign: "center", fontSize: "0.8rem", color: "var(--text-muted)" }}>
        <p>Attendance SaaS © 2026 • Enterprise Identity & Access Management</p>
      </footer>
    </div>
  );
}

export default function ActivateAccountPage() {
  return (
    <Suspense
      fallback={
        <div className="container" style={{ minHeight: "80vh", display: "flex", justifyContent: "center", alignItems: "center" }}>
          <div className="spinner-container">
            <div className="spinner" />
            <p>Loading security token validation...</p>
          </div>
        </div>
      }
    >
      <ActivateAccountContent />
    </Suspense>
  );
}
