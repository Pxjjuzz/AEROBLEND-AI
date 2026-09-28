"use client";

import { useState } from "react";

export default function SettingsPage() {
  const [cesiumToken, setCesiumToken] = useState("");
  const [defaultLat, setDefaultLat] = useState("12.9716");
  const [defaultLon, setDefaultLon] = useState("77.5946");
  const [tempUnit, setTempUnit] = useState("celsius");
  const [windUnit, setWindUnit] = useState("kmh");
  const [saved, setSaved] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  return (
    <div className="flex flex-col w-full gap-space-lg select-none max-w-4xl">
      <div>
        <div className="flex items-center gap-space-xs text-primary font-code-sm text-code-sm uppercase font-bold tracking-widest">
          <span>Platform Preferences</span>
        </div>
        <h1 className="font-headline-lg text-headline-lg text-on-surface tracking-tight mt-0.5">
          System &amp; Atmospheric Settings
        </h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          Configure default regional centroid, Cesium 3D Globe token, units, and caching horizons.
        </p>
      </div>

      {saved && (
        <div className="p-4 rounded-2xl bg-secondary-fixed text-on-secondary-fixed-variant font-label-md text-label-md flex items-center gap-2">
          <span className="material-symbols-outlined text-[20px]">check_circle</span>
          <span>Preferences saved successfully!</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="rounded-3xl bg-surface-container-lowest/80 backdrop-blur-xl p-space-lg shadow-xl border border-white/80 flex flex-col gap-6">
        {/* Default Coordinates */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="font-label-md text-label-md font-bold text-on-surface">Default Centroid Latitude</label>
            <input
              type="text"
              value={defaultLat}
              onChange={(e) => setDefaultLat(e.target.value)}
              className="px-4 py-2.5 rounded-xl bg-surface-container-low text-on-surface font-code-sm text-sm border border-surface-variant/40 focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="font-label-md text-label-md font-bold text-on-surface">Default Centroid Longitude</label>
            <input
              type="text"
              value={defaultLon}
              onChange={(e) => setDefaultLon(e.target.value)}
              className="px-4 py-2.5 rounded-xl bg-surface-container-low text-on-surface font-code-sm text-sm border border-surface-variant/40 focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>
        </div>

        {/* Cesium Ion Access Token */}
        <div className="flex flex-col gap-2">
          <label className="font-label-md text-label-md font-bold text-on-surface flex items-center justify-between">
            <span>Cesium Ion Access Token</span>
            <span className="text-xs font-normal text-on-surface-variant">Optional (Falls back to high-res ellipsoid)</span>
          </label>
          <input
            type="password"
            placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            value={cesiumToken}
            onChange={(e) => setCesiumToken(e.target.value)}
            className="w-full px-4 py-2.5 rounded-xl bg-surface-container-low text-on-surface font-code-sm text-sm border border-surface-variant/40 focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
          <span className="font-body-sm text-[11px] text-on-surface-variant">
            If provided, enables Cesium Ion photogrammetry 3D terrain and satellite basemaps.
          </span>
        </div>

        {/* Units Configuration */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
          <div className="flex flex-col gap-2">
            <label className="font-label-md text-label-md font-bold text-on-surface">Temperature Unit</label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setTempUnit("celsius")}
                className={`flex-1 py-2 rounded-xl font-label-md text-label-md font-bold transition-all ${
                  tempUnit === "celsius" ? "bg-primary text-white" : "bg-surface-container-low text-on-surface-variant"
                }`}
              >
                Celsius (°C)
              </button>
              <button
                type="button"
                onClick={() => setTempUnit("fahrenheit")}
                className={`flex-1 py-2 rounded-xl font-label-md text-label-md font-bold transition-all ${
                  tempUnit === "fahrenheit" ? "bg-primary text-white" : "bg-surface-container-low text-on-surface-variant"
                }`}
              >
                Fahrenheit (°F)
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <label className="font-label-md text-label-md font-bold text-on-surface">Wind Speed Unit</label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setWindUnit("kmh")}
                className={`flex-1 py-2 rounded-xl font-label-md text-label-md font-bold transition-all ${
                  windUnit === "kmh" ? "bg-secondary text-white" : "bg-surface-container-low text-on-surface-variant"
                }`}
              >
                km/h
              </button>
              <button
                type="button"
                onClick={() => setWindUnit("ms")}
                className={`flex-1 py-2 rounded-xl font-label-md text-label-md font-bold transition-all ${
                  windUnit === "ms" ? "bg-secondary text-white" : "bg-surface-container-low text-on-surface-variant"
                }`}
              >
                m/s
              </button>
            </div>
          </div>
        </div>

        <button
          type="submit"
          className="self-start px-6 py-2.5 rounded-full bg-primary text-white font-label-md text-label-md font-bold shadow-md hover:bg-primary/90 transition-all flex items-center gap-2 mt-2"
        >
          <span className="material-symbols-outlined text-[18px]">save</span>
          <span>Save Preferences</span>
        </button>
      </form>
    </div>
  );
}
