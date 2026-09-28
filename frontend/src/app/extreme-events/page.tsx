"use client";

import { useState, useEffect } from "react";
import { fetchExtremeEvents } from "@/lib/api";
import { useLocation } from "@/components/LocationProvider";

export default function ExtremeEventsPage() {
  const { location } = useLocation();
  const [filterSeverity, setFilterSeverity] = useState("ALL");
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchExtremeEvents(location.latitude, location.longitude, location.name);
        setEvents(res.events || []);
      } catch (e) {
        console.error("Extreme events error:", e);
        setError("Live hazard analysis could not be loaded. Please retry.");
      } finally {
        setLoading(false);
      }
  };

  useEffect(() => {
    void load();
  }, [location]);

  const filteredEvents = filterSeverity === "ALL"
    ? events
    : events.filter((e) => e.severity === filterSeverity);

  return (
    <div className="flex flex-col w-full gap-space-lg select-none">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-space-md">
        <div>
          <div className="flex items-center gap-space-xs text-error font-code-sm text-code-sm uppercase font-bold tracking-widest">
            <span className="w-2 h-2 rounded-full bg-error animate-ping" />
            <span>Hazard Intelligence &amp; Early Warning</span>
          </div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface tracking-tight mt-0.5">
            Extreme Weather Intelligence
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Automated detection of localized flash convective downpours, gale gusts, and heatwaves using multi-model thresholds.
          </p>
        </div>

        {/* Severity Filter */}
        <div className="flex items-center gap-1.5 p-1 rounded-full bg-surface-container-lowest/80 backdrop-blur-xl shadow-sm border border-white/60">
          {["ALL", "HIGH", "MODERATE", "ADVISORY"].map((sev) => (
            <button
              key={sev}
              onClick={() => setFilterSeverity(sev)}
              className={`px-3 py-1 rounded-full text-xs font-semibold transition-all ${
                filterSeverity === sev
                  ? "bg-primary text-white shadow-sm"
                  : "text-on-surface-variant hover:text-on-surface"
              }`}
            >
              {sev}
            </button>
          ))}
        </div>
      </div>

      {/* Events Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-lg">
        {loading && <div className="md:col-span-2 rounded-3xl p-space-lg bg-surface-container-lowest/80 text-on-surface-variant">Loading live hazard analysis…</div>}
        {error && <div className="md:col-span-2 rounded-3xl p-space-lg bg-error-container/30 text-on-error-container flex items-center justify-between gap-4"><span>{error}</span><button type="button" onClick={() => void load()} className="px-3 py-1.5 rounded-lg bg-error text-white font-semibold">Retry</button></div>}
        {!loading && !error && filteredEvents.length === 0 && <div className="md:col-span-2 rounded-3xl p-space-lg bg-surface-container-lowest/80 text-on-surface"><h2 className="font-bold">No active threshold events</h2><p className="mt-1 text-on-surface-variant">The live forecast for {location.name} does not currently exceed the configured rainfall, wind, or heat thresholds.</p></div>}
        {filteredEvents.map((evt, idx) => {
          const isHigh = evt.severity === "HIGH";
          return (
            <div
              key={idx}
              className={`rounded-3xl p-space-lg backdrop-blur-xl shadow-lg border transition-all flex flex-col justify-between ${
                isHigh
                  ? "bg-error-container/30 border-error/30"
                  : "bg-surface-container-lowest/80 border-white/80"
              }`}
            >
              <div className="flex flex-col gap-3">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`material-symbols-outlined text-[28px] ${isHigh ? "text-error" : "text-amber-500"}`}>
                      {evt.eventType === "HEAVY_RAINFALL" ? "warning" : evt.eventType === "HIGH_WIND" ? "air" : "thermostat"}
                    </span>
                    <div className="flex flex-col">
                      <h3 className="font-headline-sm text-headline-sm font-bold text-on-surface">
                        {evt.eventType.replace(/_/g, " ")}
                      </h3>
                      <span className="font-body-sm text-[11px] text-on-surface-variant">
                        Location: {evt.location}
                      </span>
                    </div>
                  </div>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                      isHigh ? "bg-error text-white" : "bg-amber-500/20 text-amber-800"
                    }`}
                  >
                    {evt.severity}
                  </span>
                </div>

                <p className="font-body-sm text-body-sm text-on-surface-variant leading-relaxed">
                  {evt.details}
                </p>

                <div className="grid grid-cols-3 gap-2 pt-2">
                  <div className="p-2 rounded-xl bg-surface-container-low/70 flex flex-col">
                    <span className="font-label-sm text-[10px] text-on-surface-variant">Intensity</span>
                    <span className="font-headline-sm text-headline-sm font-bold text-on-surface mt-0.5">
                      {evt.intensityValue} <span className="text-xs font-normal">{evt.unit}</span>
                    </span>
                  </div>
                  <div className="p-2 rounded-xl bg-surface-container-low/70 flex flex-col">
                    <span className="font-label-sm text-[10px] text-on-surface-variant">Duration</span>
                    <span className="font-headline-sm text-headline-sm font-bold text-on-surface mt-0.5">
                      {evt.durationHours} hrs
                    </span>
                  </div>
                  <div className="p-2 rounded-xl bg-surface-container-low/70 flex flex-col">
                    <span className="font-label-sm text-[10px] text-on-surface-variant">Agreement</span>
                    <span className="font-headline-sm text-headline-sm font-bold text-primary mt-0.5">
                      {Math.round(evt.modelAgreement * 100)}%
                    </span>
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-surface-variant/30 flex items-center justify-between text-[11px] text-on-surface-variant">
                <span>Trigger Time: <strong>{evt.time?.split("T")[1]?.slice(0, 5) || "T+0h"} UTC</strong></span>
                <span className="text-secondary font-semibold">Disaster Webhook Synced</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
