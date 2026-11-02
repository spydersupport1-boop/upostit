"use client";

import React, { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

export interface GeofenceMapProps {
  latitude: number;
  longitude: number;
  radiusMeters: number;
  isInteractive?: boolean;
  onChange?: (coords: { latitude: number; longitude: number }) => void;
  onVerify?: (coords: { latitude: number; longitude: number }) => Promise<{
    is_inside: boolean;
    distance_meters: number;
  } | null>;
  height?: string;
  locationName?: string;
}

export default function GeofenceMap({
  latitude,
  longitude,
  radiusMeters,
  isInteractive = true,
  onChange,
  onVerify,
  height = "360px",
  locationName,
}: GeofenceMapProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const circleRef = useRef<L.Circle | null>(null);
  const testMarkerRef = useRef<L.Marker | null>(null);

  const [verifyResult, setVerifyResult] = useState<{
    coords: { lat: number; lng: number };
    is_inside: boolean;
    distance: number;
  } | null>(null);
  const [isVerifying, setIsVerifying] = useState(false);
  const [testMode, setTestMode] = useState(false);

  // Initialize Map
  useEffect(() => {
    if (!mapContainerRef.current) return;

    // Check if valid lat/long provided
    const validLat = Number.isFinite(latitude) && latitude >= -90 && latitude <= 90 ? latitude : 0;
    const validLng = Number.isFinite(longitude) && longitude >= -180 && longitude <= 180 ? longitude : 0;

    const map = L.map(mapContainerRef.current, {
      center: [validLat, validLng],
      zoom: 15,
      zoomControl: true,
      attributionControl: false,
    });

    // Dark-themed or clean OpenStreetMap tile layer
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap contributors",
    }).addTo(map);

    // Custom Pin icon
    const centerPin = L.divIcon({
      className: "geofence-center-pin",
      html: `
        <div style="
          width: 28px;
          height: 28px;
          background: linear-gradient(135deg, #06b6d4, #3b82f6);
          border: 3px solid #ffffff;
          border-radius: 50% 50% 50% 0;
          transform: rotate(-45deg);
          box-shadow: 0 4px 12px rgba(6, 182, 212, 0.6);
          display: flex;
          align-items: center;
          justify-content: center;
        ">
          <div style="width: 8px; height: 8px; background: white; border-radius: 50%;"></div>
        </div>
      `,
      iconSize: [28, 28],
      iconAnchor: [14, 28],
      popupAnchor: [0, -28],
    });

    // Add Center Marker
    const marker = L.marker([validLat, validLng], {
      icon: centerPin,
      draggable: isInteractive,
    }).addTo(map);

    if (locationName) {
      marker.bindPopup(`<b>${locationName}</b><br/>Geofence Center: ${validLat.toFixed(5)}, ${validLng.toFixed(5)}`);
    }

    // Add Geofence Circle
    const circle = L.circle([validLat, validLng], {
      radius: Math.max(10, radiusMeters || 100),
      color: "#06b6d4",
      weight: 2,
      opacity: 0.85,
      fillColor: "#06b6d4",
      fillOpacity: 0.18,
      dashArray: "4, 6",
    }).addTo(map);

    markerRef.current = marker;
    circleRef.current = circle;
    mapInstanceRef.current = map;

    // Handle marker dragging
    marker.on("dragend", () => {
      const pos = marker.getLatLng();
      circle.setLatLng(pos);
      if (onChange) {
        onChange({ latitude: Number(pos.lat.toFixed(6)), longitude: Number(pos.lng.toFixed(6)) });
      }
    });

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Run once on mount

  // Handle updates to latitude, longitude, and radius
  useEffect(() => {
    const map = mapInstanceRef.current;
    const marker = markerRef.current;
    const circle = circleRef.current;
    if (!map || !marker || !circle) return;

    const validLat = Number.isFinite(latitude) && latitude >= -90 && latitude <= 90 ? latitude : 0;
    const validLng = Number.isFinite(longitude) && longitude >= -180 && longitude <= 180 ? longitude : 0;
    const newPos = L.latLng(validLat, validLng);

    marker.setLatLng(newPos);
    circle.setLatLng(newPos);
    circle.setRadius(Math.max(10, radiusMeters || 100));

    // Pan map smoothly if distance moved is significant
    const currentCenter = map.getCenter();
    if (currentCenter.distanceTo(newPos) > 5) {
      map.panTo(newPos, { animate: true });
    }
  }, [latitude, longitude, radiusMeters]);

  // Handle map click events
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    const handleClick = async (e: L.LeafletMouseEvent) => {
      const clickedLat = Number(e.latlng.lat.toFixed(6));
      const clickedLng = Number(e.latlng.lng.toFixed(6));

      if (testMode && onVerify) {
        // Test Geofence Probe Mode
        setIsVerifying(true);
        try {
          const res = await onVerify({ latitude: clickedLat, longitude: clickedLng });
          if (res) {
            setVerifyResult({
              coords: { lat: clickedLat, lng: clickedLng },
              is_inside: res.is_inside,
              distance: res.distance_meters,
            });

            // Display Test probe marker
            if (testMarkerRef.current) {
              testMarkerRef.current.remove();
            }

            const testPin = L.divIcon({
              className: "geofence-test-pin",
              html: `
                <div style="
                  width: 20px;
                  height: 20px;
                  background: ${res.is_inside ? "#10b981" : "#ef4444"};
                  border: 2px solid white;
                  border-radius: 50%;
                  box-shadow: 0 0 10px ${res.is_inside ? "rgba(16,185,129,0.8)" : "rgba(239,68,68,0.8)"};
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  color: white;
                  font-size: 11px;
                  font-weight: 800;
                ">
                  ${res.is_inside ? "✓" : "✗"}
                </div>
              `,
              iconSize: [20, 20],
              iconAnchor: [10, 10],
            });

            const tMarker = L.marker([clickedLat, clickedLng], { icon: testPin }).addTo(map);
            tMarker.bindPopup(
              `<b>${res.is_inside ? "INSIDE Geofence" : "OUTSIDE Geofence"}</b><br/>Distance: ${res.distance_meters.toFixed(1)}m<br/>Threshold: ${radiusMeters}m`
            ).openPopup();
            testMarkerRef.current = tMarker;
          }
        } finally {
          setIsVerifying(false);
        }
      } else if (isInteractive && onChange) {
        // Location Selection Mode
        onChange({ latitude: clickedLat, longitude: clickedLng });
        if (markerRef.current) markerRef.current.setLatLng(e.latlng);
        if (circleRef.current) circleRef.current.setLatLng(e.latlng);
      }
    };

    map.on("click", handleClick);
    return () => {
      map.off("click", handleClick);
    };
  }, [isInteractive, testMode, onChange, onVerify, radiusMeters]);

  return (
    <div style={{ position: "relative", width: "100%", borderRadius: "12px", overflow: "hidden", border: "1px solid var(--border-color)" }}>
      {/* Map Element */}
      <div ref={mapContainerRef} style={{ width: "100%", height, background: "#0a0e17" }} />

      {/* Floating Controls Overlay */}
      <div
        style={{
          position: "absolute",
          top: "12px",
          right: "12px",
          zIndex: 1000,
          display: "flex",
          gap: "8px",
          alignItems: "center",
          background: "rgba(17, 24, 39, 0.85)",
          backdropFilter: "blur(8px)",
          padding: "6px 10px",
          borderRadius: "8px",
          border: "1px solid var(--border-color)",
          fontSize: "0.8rem",
          color: "var(--text-primary)",
        }}
      >
        <span>Radius: <strong>{radiusMeters}m</strong></span>
        {onVerify && (
          <button
            type="button"
            className={`btn btn-sm ${testMode ? "btn-primary" : "btn-secondary"}`}
            style={{ padding: "3px 8px", fontSize: "0.75rem" }}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setTestMode(!testMode);
              if (testMarkerRef.current) {
                testMarkerRef.current.remove();
                testMarkerRef.current = null;
              }
              setVerifyResult(null);
            }}
          >
            {testMode ? "Exit Test Mode" : "🎯 Test Coordinate"}
          </button>
        )}
      </div>

      {/* Test Mode Notification / Result Bar */}
      {testMode && (
        <div
          style={{
            position: "absolute",
            bottom: "12px",
            left: "12px",
            right: "12px",
            zIndex: 1000,
            background: "rgba(17, 24, 39, 0.92)",
            backdropFilter: "blur(10px)",
            padding: "8px 14px",
            borderRadius: "8px",
            border: "1px solid var(--border-color)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            fontSize: "0.825rem",
          }}
        >
          <div>
            {isVerifying ? (
              <span style={{ color: "var(--accent-cyan)" }}>Calculating PostGIS spherical distance...</span>
            ) : verifyResult ? (
              <span>
                Coordinate ({verifyResult.coords.lat.toFixed(4)}, {verifyResult.coords.lng.toFixed(4)}):{" "}
                <strong style={{ color: verifyResult.is_inside ? "#10b981" : "#ef4444" }}>
                  {verifyResult.is_inside ? "INSIDE GEOFENCE" : "OUTSIDE GEOFENCE"}
                </strong>{" "}
                ({verifyResult.distance.toFixed(1)}m from center)
              </span>
            ) : (
              <span style={{ color: "var(--text-secondary)" }}>
                Click anywhere on the map to test whether the coordinates fall inside the PostGIS perimeter.
              </span>
            )}
          </div>
          {verifyResult && (
            <span
              style={{
                fontSize: "0.75rem",
                padding: "2px 8px",
                borderRadius: "4px",
                background: verifyResult.is_inside ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)",
                color: verifyResult.is_inside ? "#34d399" : "#f87171",
                border: `1px solid ${verifyResult.is_inside ? "rgba(16, 185, 129, 0.4)" : "rgba(239, 68, 68, 0.4)"}`,
                fontWeight: 600,
              }}
            >
              {verifyResult.is_inside ? "Pass" : "Breach"}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
