"use client";

import React, { useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import {
  locationApi,
  LocationDto,
  LocationCreateDto,
  LocationUpdateDto,
  ApiError,
} from "@/lib/api";
import LocationRosterModal from "./LocationRosterModal";

// Load Leaflet Map dynamically with SSR disabled
const GeofenceMap = dynamic(() => import("./GeofenceMap"), {
  ssr: false,
  loading: () => (
    <div
      style={{
        height: "360px",
        background: "#0a0e17",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: "12px",
        border: "1px solid var(--border-color)",
        color: "var(--text-secondary)",
        fontSize: "0.875rem",
      }}
    >
      <span className="spinner spinner-sm" style={{ marginRight: "8px" }} />
      Loading interactive geofence map...
    </div>
  ),
});

export interface LocationsTabProps {
  token: string | null;
  canManage?: boolean;
  onLocationsUpdated?: () => void;
}

export default function LocationsTab({
  token,
  canManage = true,
  onLocationsUpdated,
}: LocationsTabProps) {
  const [locations, setLocations] = useState<LocationDto[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">("all");
  const [isLoading, setIsLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [modalError, setModalError] = useState<string | null>(null);

  // Modals
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingLocation, setEditingLocation] = useState<LocationDto | null>(null);
  const [rosterLocation, setRosterLocation] = useState<LocationDto | null>(null);
  const [deactivatingLocation, setDeactivatingLocation] = useState<LocationDto | null>(null);

  // Form State
  const defaultFormState = {
    name: "",
    code: "",
    address: "",
    city: "",
    state: "",
    country_code: "US",
    postal_code: "",
    timezone: "America/New_York",
    latitude: 37.7749,
    longitude: -122.4194,
    geofence_radius_meters: 150,
    is_active: true,
    wifi_ssid: "",
    wifi_bssid: "",
    ip_range: "",
  };

  const [form, setForm] = useState(defaultFormState);

  const fetchLocations = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setErrorMessage(null);

    const activeParam = statusFilter === "active" ? true : statusFilter === "inactive" ? false : undefined;

    try {
      const resp = await locationApi.getLocations(
        {
          search: search.trim() || undefined,
          is_active: activeParam,
          limit: 100,
        },
        token
      );
      setLocations(resp.items);
      setTotal(resp.total);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else {
        setErrorMessage("Failed to load workplace locations.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [token, search, statusFilter]);

  useEffect(() => {
    fetchLocations();
  }, [fetchLocations]);

  // Open Add Modal
  const openAddModal = () => {
    setForm(defaultFormState);
    setModalError(null);
    setShowAddModal(true);
  };

  // Open Edit Modal
  const openEditModal = (loc: LocationDto) => {
    setEditingLocation(loc);
    setForm({
      name: loc.name,
      code: loc.code,
      address: loc.address || "",
      city: loc.city || "",
      state: loc.state || "",
      country_code: loc.country_code,
      postal_code: loc.postal_code || "",
      timezone: loc.timezone,
      latitude: loc.latitude,
      longitude: loc.longitude,
      geofence_radius_meters: loc.geofence_radius_meters,
      is_active: loc.is_active,
      wifi_ssid: loc.wifi_ssid || "",
      wifi_bssid: loc.wifi_bssid || "",
      ip_range: loc.ip_range || "",
    });
    setModalError(null);
  };

  // Submit Add Location
  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;

    setActionLoading("add");
    setModalError(null);

    const payload: LocationCreateDto = {
      name: form.name.trim(),
      code: form.code.trim().toUpperCase(),
      address: form.address.trim() || undefined,
      city: form.city.trim() || undefined,
      state: form.state.trim() || undefined,
      country_code: form.country_code.trim().toUpperCase(),
      postal_code: form.postal_code.trim() || undefined,
      timezone: form.timezone.trim(),
      latitude: form.latitude,
      longitude: form.longitude,
      geofence_radius_meters: form.geofence_radius_meters,
      is_active: form.is_active,
      wifi_ssid: form.wifi_ssid.trim() || undefined,
      wifi_bssid: form.wifi_bssid.trim() || undefined,
      ip_range: form.ip_range.trim() || undefined,
    };

    try {
      await locationApi.createLocation(payload, token);
      setShowAddModal(false);
      setSuccessMessage(`Workplace location "${payload.name}" created successfully.`);
      await fetchLocations();
      if (onLocationsUpdated) onLocationsUpdated();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setModalError(err.detail);
      } else {
        setModalError("Failed to create workplace location.");
      }
    } finally {
      setActionLoading(null);
    }
  };

  // Submit Edit Location
  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !editingLocation) return;

    setActionLoading("edit");
    setModalError(null);

    const payload: LocationUpdateDto = {
      name: form.name.trim(),
      code: form.code.trim().toUpperCase(),
      address: form.address.trim() || undefined,
      city: form.city.trim() || undefined,
      state: form.state.trim() || undefined,
      country_code: form.country_code.trim().toUpperCase(),
      postal_code: form.postal_code.trim() || undefined,
      timezone: form.timezone.trim(),
      latitude: form.latitude,
      longitude: form.longitude,
      geofence_radius_meters: form.geofence_radius_meters,
      is_active: form.is_active,
      wifi_ssid: form.wifi_ssid.trim() || undefined,
      wifi_bssid: form.wifi_bssid.trim() || undefined,
      ip_range: form.ip_range.trim() || undefined,
    };

    try {
      await locationApi.updateLocation(editingLocation.id, payload, token);
      setEditingLocation(null);
      setSuccessMessage(`Workplace location "${payload.name}" updated successfully.`);
      await fetchLocations();
      if (onLocationsUpdated) onLocationsUpdated();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setModalError(err.detail);
      } else {
        setModalError("Failed to update workplace location.");
      }
    } finally {
      setActionLoading(null);
    }
  };

  // Deactivate Location
  const handleDeactivate = async () => {
    if (!token || !deactivatingLocation) return;
    setActionLoading("deactivate");
    try {
      await locationApi.deactivateLocation(deactivatingLocation.id, token);
      setSuccessMessage(`Workplace location "${deactivatingLocation.name}" has been deactivated.`);
      setDeactivatingLocation(null);
      await fetchLocations();
      if (onLocationsUpdated) onLocationsUpdated();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail);
      } else {
        setErrorMessage("Failed to deactivate location.");
      }
    } finally {
      setActionLoading(null);
    }
  };

  // Geofence Coordinate Verification Callback
  const handleVerifyCoordinates = async (coords: { latitude: number; longitude: number }) => {
    if (!token) return null;
    const targetLocId = editingLocation?.id || locations[0]?.id;
    if (!targetLocId) return null;

    try {
      const resp = await locationApi.verifyCoordinates(
        {
          location_id: targetLocId,
          latitude: coords.latitude,
          longitude: coords.longitude,
        },
        token
      );
      return {
        is_inside: resp.is_inside,
        distance_meters: resp.distance_meters,
      };
    } catch {
      return null;
    }
  };

  return (
    <div>
      {/* Header & Controls */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem", marginBottom: "1.5rem" }}>
        <div>
          <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0 }}>
            Workplace Locations & Geofences
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
            Configure physical workplaces, PostGIS geofence perimeters, and employee presence boundaries.
          </p>
        </div>
        {canManage && (
          <button type="button" className="btn btn-primary btn-sm" onClick={openAddModal}>
            + Add Location
          </button>
        )}
      </div>

      {/* Global Alerts */}
      {errorMessage && (
        <div className="alert alert-danger" style={{ marginBottom: "1.25rem" }}>
          <span>{errorMessage}</span>
          <button className="alert-close" onClick={() => setErrorMessage(null)}>&times;</button>
        </div>
      )}

      {successMessage && (
        <div className="alert alert-success" style={{ marginBottom: "1.25rem" }}>
          <span>{successMessage}</span>
          <button className="alert-close" onClick={() => setSuccessMessage(null)}>&times;</button>
        </div>
      )}

      {/* Search & Status Filters */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem", marginBottom: "1.5rem" }}>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {[
            { id: "all", label: "All Locations" },
            { id: "active", label: "Active" },
            { id: "inactive", label: "Inactive" },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`btn btn-sm ${statusFilter === tab.id ? "btn-primary" : "btn-secondary"}`}
              style={{ fontSize: "0.8rem", padding: "0.35rem 0.75rem" }}
              onClick={() => setStatusFilter(tab.id as "all" | "active" | "inactive")}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <input
          type="text"
          className="search-input"
          style={{ maxWidth: "300px" }}
          placeholder="Search by name, code, or city..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Loading State */}
      {isLoading ? (
        <div className="spinner-container" style={{ padding: "3rem 0", textAlign: "center" }}>
          <div className="spinner" style={{ margin: "0 auto 1rem" }} />
          <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>Loading locations...</p>
        </div>
      ) : locations.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "3rem 1.5rem", background: "rgba(0,0,0,0.15)" }}>
          <div style={{ fontSize: "2.5rem", marginBottom: "1rem" }}>📍</div>
          <h3 style={{ fontSize: "1.1rem", fontWeight: 700, marginBottom: "0.5rem" }}>No Workplace Locations Found</h3>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", maxWidth: "420px", margin: "0 auto 1.5rem" }}>
            {search
              ? "No locations match your search query."
              : "No physical workplaces have been created yet. Define your first geofenced office or field site."}
          </p>
          {canManage && (
            <button type="button" className="btn btn-primary btn-sm" onClick={openAddModal}>
              + Create First Location
            </button>
          )}
        </div>
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Location</th>
                <th>Region & Timezone</th>
                <th>Coordinates</th>
                <th>Geofence Radius</th>
                <th>Assigned Roster</th>
                <th>Status</th>
                {canManage && <th style={{ textAlign: "right" }}>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {locations.map((loc) => (
                <tr key={loc.id}>
                  <td>
                    <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{loc.name}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      Code: <strong style={{ color: "var(--accent-cyan)" }}>{loc.code}</strong>
                    </div>
                  </td>
                  <td style={{ fontSize: "0.825rem" }}>
                    <div>{loc.city ? `${loc.city}, ${loc.country_code}` : loc.country_code}</div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{loc.timezone}</div>
                  </td>
                  <td style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                    {loc.latitude.toFixed(4)}, {loc.longitude.toFixed(4)}
                  </td>
                  <td>
                    <span className="badge" style={{ fontSize: "0.75rem" }}>
                      {loc.geofence_radius_meters}m
                    </span>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem" }}
                      onClick={() => setRosterLocation(loc)}
                    >
                      👥 {loc.employee_count} {loc.employee_count === 1 ? "Employee" : "Employees"}
                    </button>
                  </td>
                  <td>
                    {loc.is_active ? (
                      <span className="status-pill status-active">Active</span>
                    ) : (
                      <span className="status-pill status-inactive">Inactive</span>
                    )}
                  </td>
                  {canManage && (
                    <td style={{ textAlign: "right" }}>
                      <div style={{ display: "inline-flex", gap: "0.5rem" }}>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem" }}
                          onClick={() => openEditModal(loc)}
                        >
                          Edit
                        </button>
                        {loc.is_active && (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem", color: "#f87171" }}
                            onClick={() => setDeactivatingLocation(loc)}
                          >
                            Deactivate
                          </button>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* =====================================================================
          ADD / EDIT LOCATION MODAL WITH LEAFLET MAP
          ===================================================================== */}
      {(showAddModal || editingLocation) && (
        <div className="modal-overlay" onClick={() => { setShowAddModal(false); setEditingLocation(null); }}>
          <div
            className="modal-content"
            style={{ maxWidth: "860px", padding: "2.25rem" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span style={{ fontSize: "1.25rem" }}>📍</span>
                <h2 className="modal-title" style={{ margin: 0 }}>
                  {editingLocation ? `Edit Workplace: ${editingLocation.name}` : "Create Workplace Location"}
                </h2>
              </div>
              <button
                className="modal-close"
                onClick={() => { setShowAddModal(false); setEditingLocation(null); }}
              >
                &times;
              </button>
            </div>

            {modalError && (
              <div className="alert alert-danger" style={{ marginBottom: "1.25rem" }}>
                <span>{modalError}</span>
                <button className="alert-close" onClick={() => setModalError(null)}>&times;</button>
              </div>
            )}

            <form onSubmit={editingLocation ? handleEditSubmit : handleAddSubmit}>
              {/* Basic Info */}
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Location Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. San Francisco Headquarters"
                    className="form-control"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Location Code *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. HQ-SF-01"
                    className="form-control"
                    value={form.code}
                    onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
                  />
                </div>
              </div>

              {/* Address & Country/Timezone */}
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Street Address</label>
                  <input
                    type="text"
                    placeholder="100 Market St, Suite 400"
                    className="form-control"
                    value={form.address}
                    onChange={(e) => setForm({ ...form, address: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">City & State</label>
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <input
                      type="text"
                      placeholder="City"
                      className="form-control"
                      value={form.city}
                      onChange={(e) => setForm({ ...form, city: e.target.value })}
                    />
                    <input
                      type="text"
                      placeholder="State"
                      className="form-control"
                      value={form.state}
                      onChange={(e) => setForm({ ...form, state: e.target.value })}
                    />
                  </div>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Country Code (ISO 3166-1 alpha-2) *</label>
                  <input
                    type="text"
                    required
                    maxLength={2}
                    placeholder="US, IN, GB, CA..."
                    className="form-control"
                    value={form.country_code}
                    onChange={(e) => setForm({ ...form, country_code: e.target.value.toUpperCase() })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">IANA Timezone *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. America/New_York, Asia/Kolkata"
                    className="form-control"
                    value={form.timezone}
                    onChange={(e) => setForm({ ...form, timezone: e.target.value })}
                  />
                </div>
              </div>

              {/* Coordinates & Geofence Radius Slider */}
              <div style={{ background: "rgba(0,0,0,0.25)", padding: "1.25rem", borderRadius: "10px", border: "1px solid var(--border-color)", marginBottom: "1.25rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                  <h4 style={{ fontSize: "0.95rem", fontWeight: 700, margin: 0 }}>
                    Geofence Perimeter & GPS Map Picker
                  </h4>
                  <span style={{ fontSize: "0.8rem", color: "var(--accent-cyan)" }}>
                    Click map to update latitude / longitude
                  </span>
                </div>

                {/* Leaflet Map Component */}
                <div style={{ marginBottom: "1rem" }}>
                  <GeofenceMap
                    latitude={form.latitude}
                    longitude={form.longitude}
                    radiusMeters={form.geofence_radius_meters}
                    isInteractive={true}
                    locationName={form.name}
                    height="320px"
                    onChange={({ latitude, longitude }) => setForm({ ...form, latitude, longitude })}
                    onVerify={handleVerifyCoordinates}
                  />
                </div>

                <div className="form-row" style={{ alignItems: "center" }}>
                  <div className="form-group" style={{ margin: 0 }}>
                    <label className="form-label">Latitude</label>
                    <input
                      type="number"
                      step="0.000001"
                      required
                      className="form-control"
                      value={form.latitude}
                      onChange={(e) => setForm({ ...form, latitude: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                  <div className="form-group" style={{ margin: 0 }}>
                    <label className="form-label">Longitude</label>
                    <input
                      type="number"
                      step="0.000001"
                      required
                      className="form-control"
                      value={form.longitude}
                      onChange={(e) => setForm({ ...form, longitude: parseFloat(e.target.value) || 0 })}
                    />
                  </div>
                </div>

                <div className="form-group" style={{ marginTop: "1rem", marginBottom: 0 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.35rem" }}>
                    <label className="form-label" style={{ margin: 0 }}>
                      Geofence Radius: <strong>{form.geofence_radius_meters} meters</strong>
                    </label>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Min: 10m • Max: 5,000m</span>
                  </div>
                  <input
                    type="range"
                    min="10"
                    max="5000"
                    step="10"
                    style={{ width: "100%", accentColor: "var(--accent-cyan)" }}
                    value={form.geofence_radius_meters}
                    onChange={(e) => setForm({ ...form, geofence_radius_meters: parseInt(e.target.value, 10) || 100 })}
                  />
                </div>
              </div>

              {/* Optional Security Perimeter Controls */}
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Office WiFi SSID (Optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. Acme-Corp-Secure"
                    className="form-control"
                    value={form.wifi_ssid}
                    onChange={(e) => setForm({ ...form, wifi_ssid: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Allowed IP Range CIDR (Optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. 192.168.1.0/24"
                    className="form-control"
                    value={form.ip_range}
                    onChange={(e) => setForm({ ...form, ip_range: e.target.value })}
                  />
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "1.5rem" }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => { setShowAddModal(false); setEditingLocation(null); }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading !== null}
                  className="btn btn-primary"
                >
                  {actionLoading ? "Saving..." : editingLocation ? "Update Workplace" : "Create Workplace"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Confirmation Dialog: Deactivate Location */}
      {deactivatingLocation && (
        <div className="modal-overlay" onClick={() => setDeactivatingLocation(null)}>
          <div className="modal-content" style={{ maxWidth: "460px", padding: "2rem" }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ fontSize: "1.1rem", fontWeight: 700, color: "#f87171", marginBottom: "0.75rem" }}>
              Deactivate Workplace Location?
            </h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: "1.6", marginBottom: "1.5rem" }}>
              Are you sure you want to deactivate <strong>{deactivatingLocation.name}</strong> ({deactivatingLocation.code})? Existing historical employee workplace assignments and attendance logs will be preserved.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setDeactivatingLocation(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger btn-sm"
                disabled={actionLoading === "deactivate"}
                onClick={handleDeactivate}
              >
                {actionLoading === "deactivate" ? "Deactivating..." : "Confirm Deactivate"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Location Employee Roster Modal */}
      <LocationRosterModal
        isOpen={rosterLocation !== null}
        onClose={() => setRosterLocation(null)}
        location={rosterLocation}
        token={token}
      />
    </div>
  );
}
