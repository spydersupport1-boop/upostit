"use client";

import React from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import LocationsTab from "@/components/LocationsTab";

export default function LocationsPage() {
  const { user, tenant, token, isAuthenticated, isLoading: isAuthLoading, logout } = useAuth();

  if (isAuthLoading) {
    return (
      <div className="container">
        <div className="spinner-container">
          <div className="spinner" />
          <p>Verifying secure session...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="container">
        <nav className="navbar">
          <div className="logo-badge">
            <div className="logo-dot" />
            <Link href="/">Attendance SaaS</Link>
            <span className="badge">Workplaces</span>
          </div>
          <div>
            <Link href="/organization" className="btn btn-primary btn-sm">
              Sign In to Access Workplaces
            </Link>
          </div>
        </nav>

        <div className="card" style={{ maxWidth: "520px", margin: "4rem auto", textAlign: "center", padding: "3rem 2rem" }}>
          <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>📍</div>
          <h2 style={{ fontSize: "1.5rem", fontWeight: 800, marginBottom: "0.5rem" }}>
            Authentication Required
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", lineHeight: "1.6", marginBottom: "2rem" }}>
            Workplace locations and PostGIS geofence perimeters are protected by enterprise multi-tenant Row-Level Security. Please sign in to your company workspace to view locations.
          </p>
          <Link href="/organization" className="btn btn-primary">
            Sign In with Workspace Credentials →
          </Link>
        </div>
      </div>
    );
  }

  const canManage = user?.role === "owner" || user?.role === "admin" || user?.role === "hr";

  return (
    <div className="container">
      {/* Navigation Header */}
      <nav className="navbar">
        <div className="logo-badge">
          <div className="logo-dot" />
          <Link href="/">Attendance SaaS</Link>
          <span className="badge">Workplace Locations</span>
        </div>
        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          <Link href="/organization" className="btn btn-secondary btn-sm">
            ← Organization Console
          </Link>
          <span className={`badge badge-role-${user?.role || "admin"}`}>
            Role: {user?.role ? user.role.toUpperCase() : "AUTHENTICATED"}
          </span>
          <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            {user?.full_name} ({tenant?.name})
          </span>
          <button className="btn btn-secondary btn-sm" onClick={logout}>
            Sign Out
          </button>
        </div>
      </nav>

      {/* Main Locations Management Component */}
      <LocationsTab token={token} canManage={canManage} />
    </div>
  );
}
