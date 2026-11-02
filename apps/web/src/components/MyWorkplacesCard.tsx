"use client";

import React, { useState, useEffect, useCallback } from "react";
import { assignmentApi, WorkplaceAssignmentDto, ApiError } from "@/lib/api";

export interface MyWorkplacesCardProps {
  token: string | null;
}

export default function MyWorkplacesCard({ token }: MyWorkplacesCardProps) {
  const [workplaces, setWorkplaces] = useState<WorkplaceAssignmentDto[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fetchMyWorkplaces = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const resp = await assignmentApi.getMyWorkplaces(token);
      setWorkplaces(resp.items);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else {
        setErrorMessage("Failed to load your assigned workplaces.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchMyWorkplaces();
  }, [fetchMyWorkplaces]);

  const todayStr = new Date().toISOString().split("T")[0];
  const activeWorkplaces = workplaces.filter((w) => !w.effective_to || w.effective_to >= todayStr);

  return (
    <div className="card" style={{ maxWidth: "720px", margin: "2rem auto", padding: "2rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ fontSize: "1.25rem" }}>📍</span>
          <h2 style={{ fontSize: "1.2rem", fontWeight: 700, margin: 0 }}>
            My Assigned Workplaces
          </h2>
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={fetchMyWorkplaces}
          disabled={isLoading}
        >
          Refresh
        </button>
      </div>

      <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginBottom: "1.5rem" }}>
        Locations where you are authorized to log attendance sessions within PostGIS geofence perimeters.
      </p>

      {errorMessage && (
        <div className="alert alert-danger" style={{ marginBottom: "1.25rem" }}>
          <span>{errorMessage}</span>
        </div>
      )}

      {isLoading ? (
        <div className="spinner-container" style={{ padding: "1.5rem 0", textAlign: "center" }}>
          <div className="spinner" style={{ margin: "0 auto 0.75rem" }} />
          <p style={{ color: "var(--text-muted)", fontSize: "0.825rem" }}>Loading your workplaces...</p>
        </div>
      ) : activeWorkplaces.length === 0 ? (
        <div style={{ textAlign: "center", padding: "1.75rem", background: "rgba(0,0,0,0.15)", borderRadius: "8px" }}>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0 }}>
            No active workplace locations currently assigned to your profile. Contact your HR administrator.
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {activeWorkplaces.map((wp) => (
            <div
              key={wp.id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "1rem 1.25rem",
                background: "rgba(0,0,0,0.25)",
                borderRadius: "10px",
                border: "1px solid var(--border-color)",
              }}
            >
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <strong style={{ color: "var(--text-primary)", fontSize: "0.95rem" }}>{wp.location_name}</strong>
                  {wp.is_primary && (
                    <span className="badge badge-green" style={{ fontSize: "0.7rem", padding: "0.15rem 0.5rem" }}>
                      ★ Primary
                    </span>
                  )}
                </div>
                <div style={{ fontSize: "0.775rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                  Code: <span style={{ color: "var(--accent-cyan)" }}>{wp.location_code}</span> • Effective from {wp.effective_from}
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <span className="status-pill status-active">Authorized</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
