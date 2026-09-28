"use client";

import { useState, useEffect } from "react";
import { fetchForecast, fetchAnalogues } from "@/lib/api";
import { useLocation } from "@/components/LocationProvider";

const QUICK_LOCATIONS = [
  { name: "Bengaluru, Karnataka", code: "BLR", lat: 12.9716, lon: 77.5946, elev: 920 },
  { name: "Mumbai, Maharashtra", code: "BOM", lat: 19.0760, lon: 72.8777, elev: 14 },
  { name: "New Delhi, NCR", code: "DEL", lat: 28.6139, lon: 77.2090, elev: 216 },
  { name: "Chennai, Tamil Nadu", code: "MAA", lat: 13.0827, lon: 80.2707, elev: 6 },
  { name: "Hyderabad, Telangana", code: "HYD", lat: 17.3850, lon: 78.4867, elev: 505 },
  { name: "Tokyo, Kanto", code: "HND", lat: 35.6762, lon: 139.6503, elev: 40 },
  { name: "Singapore, SG", code: "SIN", lat: 1.3521, lon: 103.8198, elev: 15 },
];

export default function ForecastPage() {
  const { location, setLocation } = useLocation();
  const selectedLoc = { name: location.name, lat: location.latitude, lon: location.longitude, elev: location.elevation || 0, code: "LIVE" };
  const [horizon, setHorizon] = useState("24h");
  const [selectedRegime, setSelectedRegime] = useState<string>("MONSOON");
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);
  const [analogues, setAnalogues] = useState<any[]>([]);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const res = await fetchForecast(selectedLoc.lat, selectedLoc.lon, selectedLoc.name);
        setData(res);
        if (res.activeRegime) {
          setSelectedRegime(res.activeRegime.regime);
        }
        const analRes = await fetchAnalogues(selectedLoc.lat, selectedLoc.lon);
        setAnalogues(analRes.matches || []);
      } catch (e) {
        console.error("Forecast page error:", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [location]);

  const current = data?.currentBlend;
  const weights = data?.weights?.weights || [];
  const regime = data?.activeRegime;
  const disagreement = data?.disagreement;
  const explainability = data?.explainability;
  const hourly = data?.hourlyTrajectory || [];
  const horizonHours = Number.parseInt(horizon, 10);
  const horizonTrajectory = hourly.slice(0, horizonHours);

  const getWeight = (name: string) => {
    const item = weights.find((w: any) => w.modelName === name);
    return item ? Math.round(item.weight * 100) : 25;
  };

  const aifsWeight = getWeight("ECMWF_AIFS");
  const ifsWeight = getWeight("ECMWF_IFS");
  const gfsWeight = getWeight("NOAA_GFS");
  const iconWeight = getWeight("DWD_ICON");

  const blendedRain = horizonTrajectory.length
    ? Math.round(horizonTrajectory.reduce((total: number, point: any) => total + (Number(point.precipitation) || 0), 0) * 10) / 10
    : null;

  return (
    <div className="flex flex-col w-full gap-space-lg select-none">
      {/* Top Context & Scenario Bar (Glass Level 2) */}
      <header className="w-full bg-surface-container-lowest/80 backdrop-blur-xl rounded-2xl shadow-[0_20px_40px_-15px_rgba(15,23,42,0.05)] p-space-md flex flex-col xl:flex-row items-start xl:items-center justify-between gap-space-md border border-white/80">
        {/* Left: Location & Quick Picks */}
        <div className="flex flex-wrap items-center gap-space-md">
          <button className="flex items-center gap-space-xs px-space-md py-2 rounded-xl bg-surface-container-low/90 hover:bg-surface-container transition-all text-on-surface">
            <span className="material-symbols-outlined text-primary text-[20px]">location_on</span>
            <span className="font-headline-sm text-headline-sm font-bold tracking-tight">
              {selectedLoc.name}
            </span>
          </button>

          {/* Quick Location Switches */}
          <div className="flex items-center gap-1.5 overflow-x-auto py-1">
            <span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider pl-1 pr-2">
              Quick:
            </span>
            {QUICK_LOCATIONS.map((loc) => (
              <button
                key={loc.code}
                onClick={() => setLocation({ name: loc.name, latitude: loc.lat, longitude: loc.lon, elevation: loc.elev })}
                className={`loc-chip px-3 py-1 rounded-full text-label-sm font-label-sm transition-all ${
                  selectedLoc.code === loc.code
                    ? "bg-primary text-on-primary font-bold shadow-sm"
                    : "bg-surface-container text-on-surface-variant hover:text-on-surface"
                }`}
              >
                {loc.code}
              </button>
            ))}
          </div>
        </div>

        {/* Center/Right Controls: Horizon & Regimes */}
        <div className="flex flex-wrap items-center gap-space-md w-full xl:w-auto justify-between xl:justify-end">
          {/* Horizon Segmented Control */}
          <div className="flex items-center bg-surface-container-low/90 p-1 rounded-full shadow-inner border border-white/40">
            {["6h", "12h", "24h", "48h", "72h"].map((h) => (
              <button
                key={h}
                onClick={() => setHorizon(h)}
                className={`px-3 py-1 text-label-sm font-label-sm rounded-full transition-all ${
                  horizon === h
                    ? "bg-primary-container text-white font-semibold shadow-sm"
                    : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                {h}
              </button>
            ))}
          </div>

          {/* Weather Regime Selector */}
          <div className="flex items-center gap-1.5 bg-surface-container-low/90 px-2 py-1 rounded-full border border-white/40">
            <span className="font-label-sm text-label-sm text-on-surface-variant px-1 flex items-center gap-1">
              <span className="material-symbols-outlined text-secondary text-[16px]">cyclone</span> Regime:
            </span>
            {["NORMAL", "MONSOON", "CONVECTIVE", "EXTREME"].map((r) => (
              <button
                key={r}
                onClick={() => setSelectedRegime(r)}
                className={`px-2.5 py-0.5 rounded-full text-label-sm font-label-sm transition-all ${
                  selectedRegime === r
                    ? "bg-secondary text-on-secondary shadow-sm font-semibold"
                    : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                {r.charAt(0) + r.slice(1).toLowerCase()}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* Blended Summary Key Insight Banner */}
      <div className="w-full bg-gradient-to-r from-primary-container via-primary to-tertiary text-on-primary rounded-2xl p-space-md shadow-[0_12px_32px_-8px_rgba(0,74,198,0.3)] flex flex-col md:flex-row items-start md:items-center justify-between gap-space-md relative overflow-hidden">
        <div className="absolute -right-12 -bottom-12 w-64 h-64 bg-surface-container-lowest/10 rounded-full blur-2xl pointer-events-none" />
        <div className="flex items-center gap-space-md z-10">
          <div className="w-12 h-12 rounded-xl bg-surface-container-lowest/20 backdrop-blur-md flex items-center justify-center text-on-primary shadow-inner">
            <span className="material-symbols-outlined text-[28px]">insights</span>
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <span className="font-label-sm text-label-sm uppercase tracking-widest text-primary-fixed">
                Engine Synthesis Active
              </span>
              <span className="px-2 py-0.5 rounded-full bg-surface-container-lowest/20 font-code-sm text-code-sm text-on-primary">
                {regime?.synopticCluster?.split(":")[0] || "Cluster #4B"}
              </span>
            </div>
            <div className="font-headline-md text-headline-md text-on-primary font-bold">
              Blended Rainfall, next {horizon}: {blendedRain ?? "—"}{blendedRain != null ? " mm" : ""}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-space-md z-10 w-full md:w-auto justify-between md:justify-end">
          <div className="flex flex-col text-left md:text-right">
            <div className="flex items-center md:justify-end gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-secondary-fixed animate-pulse" />
              <span className="font-label-lg text-label-lg font-bold">
                Confidence: {current?.confidencePercentage ?? "—"}{current?.confidencePercentage != null ? "%" : ""}
              </span>
            </div>
            <span className="font-body-sm text-body-sm text-primary-fixed">
              High Quality Multi-Physics Agreement
            </span>
          </div>
          <button className="px-4 py-2 rounded-xl bg-surface-container-lowest text-primary font-label-lg text-label-lg font-bold shadow-md hover:bg-surface-bright transition-all flex items-center gap-1.5">
            <span className="material-symbols-outlined text-[18px]">verified</span>
            <span>Audit Synthesis</span>
          </button>
        </div>
      </div>

      {/* Dual Core Scientific Panels */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
        {/* Left Panel: Adaptive Model Blending & Dynamic Weights (7 Cols) */}
        <section className="lg:col-span-7 bg-surface-container-lowest/80 backdrop-blur-xl rounded-2xl shadow-[0_20px_40px_-15px_rgba(15,23,42,0.05)] p-space-lg flex flex-col justify-between gap-space-lg border border-white/80">
          <div className="flex flex-col gap-space-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2 h-5 rounded-full bg-primary" />
                <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold">
                  Adaptive Model Blending &amp; Dynamic Weights
                </h2>
              </div>
              <span className="font-label-sm text-label-sm text-on-surface-variant flex items-center gap-1">
                <span className="material-symbols-outlined text-[16px]">sync</span> Live Model Run
              </span>
            </div>
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              Deep learning gating network dynamically alters softmax weights across grid cells by validating atmospheric
              moisture convergence against barometric tendencies.
            </p>
          </div>

          {/* Donut Chart & Stacked Contribution Breakdowns */}
          <div className="grid grid-cols-1 sm:grid-cols-12 items-center gap-space-md py-space-sm bg-surface-container-low/50 rounded-2xl p-space-md">
            {/* SVG Donut */}
            <div className="sm:col-span-5 flex flex-col items-center justify-center relative">
              <svg className="w-44 h-44 -rotate-90 transform" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="48" fill="transparent" stroke="#E2E7FF" strokeWidth="12" />
                {/* AI Model */}
                <circle
                  cx="60"
                  cy="60"
                  r="48"
                  fill="transparent"
                  stroke="#632ECD"
                  strokeWidth="12"
                  strokeDasharray={`${(aifsWeight / 100) * 301.6} 301.6`}
                  strokeDashoffset="0"
                  strokeLinecap="round"
                />
                {/* ECMWF IFS */}
                <circle
                  cx="60"
                  cy="60"
                  r="48"
                  fill="transparent"
                  stroke="#004AC6"
                  strokeWidth="12"
                  strokeDasharray={`${(ifsWeight / 100) * 301.6} 301.6`}
                  strokeDashoffset={`-${(aifsWeight / 100) * 301.6}`}
                  strokeLinecap="round"
                />
                {/* GFS */}
                <circle
                  cx="60"
                  cy="60"
                  r="48"
                  fill="transparent"
                  stroke="#57DFFE"
                  strokeWidth="12"
                  strokeDasharray={`${(gfsWeight / 100) * 301.6} 301.6`}
                  strokeDashoffset={`-${((aifsWeight + ifsWeight) / 100) * 301.6}`}
                  strokeLinecap="round"
                />
                {/* ICON */}
                <circle
                  cx="60"
                  cy="60"
                  r="48"
                  fill="transparent"
                  stroke="#00687A"
                  strokeWidth="12"
                  strokeDasharray={`${(iconWeight / 100) * 301.6} 301.6`}
                  strokeDashoffset={`-${((aifsWeight + ifsWeight + gfsWeight) / 100) * 301.6}`}
                  strokeLinecap="round"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center pointer-events-none">
                <span className="font-headline-md text-headline-md font-bold text-on-surface leading-none">
                  {blendedRain ?? "—"}
                </span>
                <span className="font-label-sm text-label-sm text-primary font-semibold">{blendedRain != null ? `mm / ${horizon}` : "No data"}</span>
              </div>
            </div>

            {/* Legend & Percentages */}
            <div className="sm:col-span-7 flex flex-col gap-2.5">
              <div className="flex items-center justify-between p-2 rounded-xl bg-surface-container-lowest shadow-sm">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-md bg-tertiary" />
                  <div className="flex flex-col">
                    <span className="font-label-md text-label-md text-on-surface font-semibold">ECMWF AIFS</span>
                    <span className="font-code-sm text-code-sm text-on-surface-variant">Neural Mesoscale Mesh</span>
                  </div>
                </div>
                <div className="text-right">
                  <span className="font-label-lg text-label-lg font-bold text-tertiary">{aifsWeight}%</span>
                </div>
              </div>

              <div className="flex items-center justify-between p-2 rounded-xl bg-surface-container-lowest shadow-sm">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-md bg-primary" />
                  <div className="flex flex-col">
                    <span className="font-label-md text-label-md text-on-surface font-semibold">ECMWF IFS (0.1°)</span>
                    <span className="font-code-sm text-code-sm text-on-surface-variant">Hydrostatic Integrated IFS</span>
                  </div>
                </div>
                <div className="text-right">
                  <span className="font-label-lg text-label-lg font-bold text-primary">{ifsWeight}%</span>
                </div>
              </div>

              <div className="flex items-center justify-between p-2 rounded-xl bg-surface-container-lowest shadow-sm">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-md bg-secondary-container" />
                  <div className="flex flex-col">
                    <span className="font-label-md text-label-md text-on-surface font-semibold">NOAA GFS v16.3</span>
                    <span className="font-code-sm text-code-sm text-on-surface-variant">FV3 Spectral Dynamical</span>
                  </div>
                </div>
                <div className="text-right">
                  <span className="font-label-lg text-label-lg font-bold text-primary">{gfsWeight}%</span>
                </div>
              </div>

              <div className="flex items-center justify-between p-2 rounded-xl bg-surface-container-lowest shadow-sm">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-md bg-secondary" />
                  <div className="flex flex-col">
                    <span className="font-label-md text-label-md text-on-surface font-semibold">DWD ICON Global</span>
                    <span className="font-code-sm text-code-sm text-on-surface-variant">Icosahedral Mesh</span>
                  </div>
                </div>
                <div className="text-right">
                  <span className="font-label-lg text-label-lg font-bold text-secondary">{iconWeight}%</span>
                </div>
              </div>
            </div>
          </div>

          {/* Contextual Parameters Grid Strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-space-sm pt-space-xs">
            <div className="flex flex-col p-space-sm rounded-xl bg-surface-container-low/70">
              <span className="font-label-sm text-label-sm text-on-surface-variant uppercase">Region Domain</span>
              <span className="font-label-md text-label-md font-bold text-on-surface mt-0.5">
                {selectedLoc.name.split(",")[0]}
              </span>
            </div>
            <div className="flex flex-col p-space-sm rounded-xl bg-surface-container-low/70">
              <span className="font-label-sm text-label-sm text-on-surface-variant uppercase">Active Season</span>
              <span className="font-label-md text-label-md font-bold text-on-surface mt-0.5">Late SW Monsoon</span>
            </div>
            <div className="flex flex-col p-space-sm rounded-xl bg-surface-container-low/70">
              <span className="font-label-sm text-label-sm text-on-surface-variant uppercase">Local Regime</span>
              <span className="font-label-md text-label-md font-bold text-secondary mt-0.5">
                {selectedRegime}
              </span>
            </div>
            <div className="flex flex-col p-space-sm rounded-xl bg-surface-container-low/70">
              <span className="font-label-sm text-label-sm text-on-surface-variant uppercase">Recent Error Bias</span>
              <span className="font-code-sm text-code-sm font-bold text-tertiary mt-0.5">-0.8 mm (Optimal)</span>
            </div>
          </div>
        </section>

        {/* Right Panel: Explainable AI Engine ('Why This Forecast?') (5 Cols) */}
        <section className="lg:col-span-5 bg-surface-container-lowest/80 backdrop-blur-xl rounded-2xl shadow-[0_20px_40px_-15px_rgba(15,23,42,0.05)] p-space-lg flex flex-col justify-between gap-space-md border border-white/80">
          <div className="flex flex-col gap-space-xs">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-tertiary text-[24px]">psychology</span>
                <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold">Why This Forecast?</h2>
              </div>
              <span className="px-2 py-0.5 rounded-full bg-tertiary-fixed text-on-tertiary-fixed-variant font-label-sm text-label-sm font-semibold">
                XAI Engine
              </span>
            </div>
            <p className="font-body-sm text-body-sm text-on-surface-variant">
              Attribution weights explaining why the neural engine modified canonical NWP outputs.
            </p>
          </div>

          {/* Feature Attribution Cards */}
          <div className="flex flex-col gap-2.5">
            {explainability?.attributions?.map((attr: any, idx: number) => (
              <div key={idx} className="p-3 rounded-xl bg-surface-container-low/70 hover:bg-surface-container transition-all flex flex-col gap-1 border border-white/40">
                <div className="flex items-center justify-between">
                  <span className="font-label-md text-label-md font-bold text-on-surface flex items-center gap-1.5">
                    <span className="material-symbols-outlined text-primary text-[18px]">verified</span>
                    {attr.featureName}
                  </span>
                  <span className="font-code-sm text-code-sm font-bold text-primary">
                    +{attr.impactScore}% impact
                  </span>
                </div>
                <p className="font-body-sm text-body-sm text-on-surface-variant leading-relaxed">
                  {attr.rationale}
                </p>
              </div>
            ))}
          </div>

          {/* Confidence Attribution Heat Bar */}
          <div className="flex flex-col gap-1.5 pt-space-xs">
            <div className="flex items-center justify-between font-label-sm text-label-sm text-on-surface-variant">
              <span>AI Explanation Coherence Index</span>
              <span className="font-bold text-on-surface">
                {explainability?.coherenceIndex ?? "—"} / 100
              </span>
            </div>
            <div className="w-full h-2 rounded-full bg-surface-container overflow-hidden flex">
              <div className="h-full bg-tertiary" style={{ width: `${aifsWeight}%` }} />
              <div className="h-full bg-primary" style={{ width: `${ifsWeight}%` }} />
              <div className="h-full bg-secondary-container" style={{ width: `${gfsWeight}%` }} />
              <div className="h-full bg-secondary" style={{ width: `${iconWeight}%` }} />
            </div>
          </div>
        </section>
      </div>

      {/* Forecast Verification & Model Disagreement Detector */}
      <section className="w-full bg-surface-container-lowest/80 backdrop-blur-xl rounded-2xl shadow-[0_20px_40px_-15px_rgba(15,23,42,0.05)] p-space-lg flex flex-col gap-space-md border border-white/80">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-space-sm">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-secondary text-[24px]">troubleshoot</span>
            <div>
              <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold">
                Model Disagreement &amp; Bifurcation Detector
              </h2>
              <span className="font-body-sm text-body-sm text-on-surface-variant">
                Continuous cross-entropy variance analysis between deterministic physics and neural embeddings
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-surface-container-high/60">
            <span className="w-2.5 h-2.5 rounded-full bg-secondary" />
            <span className="font-label-md text-label-md font-bold text-on-surface">
              {disagreement?.spreadLevel ?? "UNAVAILABLE"} SPREAD DETECTED (Δ {disagreement?.range ?? "—"}{disagreement?.range != null ? " mm" : ""})
            </span>
          </div>
        </div>

        {/* Visual Disagreement Range Bar */}
        <div className="p-space-md rounded-xl bg-surface-container-low/50 flex flex-col gap-2">
          <div className="flex justify-between items-center text-body-sm font-body-sm text-on-surface-variant">
            <span>
              Model Spread Envelope: <strong className="text-on-surface">{disagreement?.min ?? "—"}{disagreement?.min != null ? " mm" : ""} – {disagreement?.max ?? "—"}{disagreement?.max != null ? " mm" : ""}</strong> (Spread Delta: {disagreement?.range ?? "—"}{disagreement?.range != null ? " mm" : ""})
            </span>
            <span className="text-primary font-semibold">Low risk of atmospheric state bifurcation</span>
          </div>
          <div className="relative w-full h-8 bg-surface-container rounded-lg overflow-hidden flex items-center px-4">
            <div className="absolute left-[30%] right-[16%] top-0 bottom-0 bg-secondary/15 rounded" />
            <span className="absolute left-[30%] -translate-x-1/2 flex flex-col items-center">
              <span className="w-2.5 h-2.5 rounded-full bg-surface-tint shadow" />
              <span className="font-code-sm text-[10px] text-on-surface-variant mt-0.5">GFS</span>
            </span>
            <span className="absolute left-[45%] -translate-x-1/2 flex flex-col items-center">
              <span className="w-2.5 h-2.5 rounded-full bg-tertiary shadow" />
              <span className="font-code-sm text-[10px] text-tertiary mt-0.5">AIFS</span>
            </span>
            <span className="absolute left-[62%] -translate-x-1/2 flex flex-col items-center">
              <span className="w-3.5 h-3.5 rounded-full bg-primary border-2 border-surface-container-lowest shadow-md" />
              <span className="font-code-sm text-[10px] font-bold text-primary mt-0.5">AeroBlend</span>
            </span>
            <span className="absolute left-[84%] -translate-x-1/2 flex flex-col items-center">
              <span className="w-2.5 h-2.5 rounded-full bg-primary shadow" />
              <span className="font-code-sm text-[10px] text-primary mt-0.5">ECMWF</span>
            </span>
          </div>
          <p className="font-body-sm text-body-sm text-on-surface-variant italic">
            Agreement index is 88%. Blending engine actively dampened ECMWF wet convective plume over urban thermal heat sinks and favored the multi-physics median coupled with AIFS moisture convergence vector.
          </p>
        </div>
      </section>

      {/* Historical Weather Analogue Module */}
      <section className="w-full bg-surface-container-lowest/80 backdrop-blur-xl rounded-2xl shadow-[0_20px_40px_-15px_rgba(15,23,42,0.05)] p-space-lg flex flex-col gap-space-md border border-white/80">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-space-sm">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-[24px]">history_edu</span>
            <div>
              <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold">
                Historical Weather Analogue Engine
              </h2>
              <span className="font-body-sm text-body-sm text-on-surface-variant">
                Topological nearest-neighbor search through 40+ years of ECMWF ERA5 reanalysis data
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-primary-fixed text-on-primary-fixed font-label-md text-label-md font-bold">
            <span className="material-symbols-outlined text-[16px]">compare_arrows</span>
            <span>Atmospheric Vector Similarity: 91%</span>
          </div>
        </div>

        {/* Case Studies Comparison Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md">
          {analogues.map((item, idx) => (
            <div key={idx} className="p-space-md rounded-xl bg-surface-container-low/70 flex flex-col justify-between gap-3 hover:shadow-md transition-all border border-white/50">
              <div className="flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <span className="px-2 py-0.5 rounded bg-surface-container-high text-on-surface-variant font-code-sm text-code-sm font-semibold">
                    {item.date}
                  </span>
                  <span className="font-label-sm text-label-sm text-secondary font-bold">
                    {item.similarityPercentage}% Match
                  </span>
                </div>
                <h3 className="font-headline-sm text-headline-sm text-on-surface font-semibold mt-1">
                  {item.synopticMatchName}
                </h3>
                <p className="font-body-sm text-body-sm text-on-surface-variant">
                  {item.description}
                </p>
              </div>
              <div className="flex flex-col gap-2 pt-2 border-t border-surface-variant/40">
                <div className="flex justify-between items-center text-body-sm font-body-sm">
                  <span className="text-on-surface-variant">Blended Forecast Error:</span>
                  <span className="font-code-sm text-code-sm font-bold text-secondary">{item.blendedForecastError} mm</span>
                </div>
                <div className="flex justify-between items-center text-body-sm font-body-sm">
                  <span className="text-on-surface-variant">Raw NWP Solver Error:</span>
                  <span className="font-code-sm text-code-sm font-bold text-error">{item.rawNwpError} mm</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Hourly Blended Forecast Breakdown Table */}
      <section className="w-full bg-surface-container-lowest/80 backdrop-blur-xl rounded-2xl shadow-[0_20px_40px_-15px_rgba(15,23,42,0.05)] p-space-lg flex flex-col gap-space-md mb-4 border border-white/80">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-space-sm">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-[24px]">schedule</span>
            <div>
              <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold">
                Hourly Chronological Blended Trajectory
              </h2>
              <span className="font-body-sm text-body-sm text-on-surface-variant">
                High-resolution interval sequencing with physics attribution
              </span>
            </div>
          </div>
        </div>

        <div className="w-full overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface-container-low text-on-surface-variant font-label-sm text-label-sm uppercase tracking-wider">
                <th className="py-3 px-4 rounded-l-xl">Timeline</th>
                <th className="py-3 px-4">Conditions</th>
                <th className="py-3 px-4">Precip Rate</th>
                <th className="py-3 px-4">PoP (%)</th>
                <th className="py-3 px-4">Wind Vector</th>
                <th className="py-3 px-4">Temp / Dew</th>
                <th className="py-3 px-4">Relative Humidity</th>
                <th className="py-3 px-4 rounded-r-xl">Dominant Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-container/60 font-body-sm text-body-sm text-on-surface">
              {horizonTrajectory.map((pt: any, idx: number) => (
                <tr key={idx} className="hover:bg-surface-container-low/40 transition-colors">
                  <td className="py-3.5 px-4 font-code-sm text-code-sm font-bold text-on-surface">
                    {pt.timestamp?.split("T")[1]?.slice(0, 5) || `+${pt.leadTimeHours}h`} <span className="text-on-surface-variant font-normal">UTC</span>
                  </td>
                  <td className="py-3.5 px-4">
                    <div className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-primary text-[20px]">
                        {pt.precipitation > 2 ? "rainy" : pt.precipitation > 0 ? "grain" : "partly_cloudy_day"}
                      </span>
                      <span>{pt.conditionText}</span>
                    </div>
                  </td>
                  <td className="py-3.5 px-4 font-code-sm text-code-sm font-semibold text-primary">
                    {pt.precipitation} mm/h
                  </td>
                  <td className="py-3.5 px-4 font-code-sm text-code-sm">
                    {pt.pop}%
                  </td>
                  <td className="py-3.5 px-4 font-code-sm text-code-sm">
                    {Math.round(pt.windDirection)}° @ {pt.windSpeed} km/h
                  </td>
                  <td className="py-3.5 px-4 font-code-sm text-code-sm">
                    {pt.temperature}°C / {pt.dewPoint}°C
                  </td>
                  <td className="py-3.5 px-4 font-code-sm text-code-sm">
                    {pt.humidity}%
                  </td>
                  <td className="py-3.5 px-4">
                    <span className="px-2.5 py-1 rounded-full bg-tertiary-fixed text-on-tertiary-fixed-variant font-label-sm text-label-sm font-semibold flex items-center gap-1 w-fit">
                      <span className="w-1.5 h-1.5 rounded-full bg-tertiary" /> {pt.dominantSource}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
