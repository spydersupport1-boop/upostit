import React from "react";

export default function Home() {
  return (
    <div className="container">
      <nav className="navbar">
        <div className="logo-badge">
          <div className="logo-dot" />
          <span>Attendance SaaS</span>
          <span className="badge">Phase 1</span>
        </div>
        <div>
          <span className="badge badge-green">Monorepo Active</span>
        </div>
      </nav>

      <section className="hero">
        <h1>Workforce Presence Engineered for Integrity</h1>
        <p>
          Eliminate proxy check-ins, mock GPS, and ghost shifts with automated PostGIS geofencing,
          facial liveness detection, and an append-only audit trail.
        </p>
      </section>

      <div className="grid">
        <div className="card">
          <div className="card-title">
            <span>📱</span> Flutter Native Mobile App
          </div>
          <p className="card-desc">
            Cross-platform Flutter app for iOS and Android with offline-first event queuing,
            biometric liveness, and native GPS geofencing.
          </p>
          <div className="code-block">cd apps/mobile && flutter run</div>
        </div>

        <div className="card">
          <div className="card-title">
            <span>⚡</span> FastAPI Modular Monolith
          </div>
          <p className="card-desc">
            High-performance asynchronous backend with SQLAlchemy 2, Pydantic v2, and
            strict per-transaction Row-Level Security.
          </p>
          <div className="code-block">GET http://localhost:8000/health</div>
        </div>

        <div className="card">
          <div className="card-title">
            <span>🔒</span> Supabase PostgreSQL + PostGIS
          </div>
          <p className="card-desc">
            Single multi-tenant database of record with PostGIS spatial calculations,
            Row-Level Security (RLS), and zero local Postgres duplicate containers.
          </p>
          <div className="code-block">make verify-db</div>
        </div>
      </div>

      <footer className="footer">
        <p>Attendance SaaS © 2026 • Stage A: Foundation • Phase 1 Setup</p>
      </footer>
    </div>
  );
}
