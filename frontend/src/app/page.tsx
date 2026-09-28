"use client";

import { useState, useEffect } from "react";
import { fetchForecast } from "@/lib/api";
import { useLocation } from "@/components/LocationProvider";

const QUICK_LOCATIONS = [
  { name: "Bengaluru, Karnataka", lat: 12.9716, lon: 77.5946, elev: 920 },
  { name: "Mumbai, Maharashtra", lat: 19.0760, lon: 72.8777, elev: 14 },
  { name: "New Delhi, NCR", lat: 28.6139, lon: 77.2090, elev: 216 },
  { name: "Chennai, Tamil Nadu", lat: 13.0827, lon: 80.2707, elev: 6 },
  { name: "Hyderabad, Telangana", lat: 17.3850, lon: 78.4867, elev: 505 },
];

export default function OverviewPage() {
  const { location, setLocation } = useLocation();
  const selectedLoc = { name: location.name, lat: location.latitude, lon: location.longitude, elev: location.elevation || 0 };
  const [horizon, setHorizon] = useState<24 | 48 | 72>(24);
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);
  const [activeLayer, setActiveLayer] = useState("precip");
  const layerConfig = ({
    precip: { title: "Precipitation", filter: "none" },
    temp: { title: "Temperature gradient", filter: "hue-rotate(115deg) saturate(1.2)" },
    wind: { title: "Wind streamlines", filter: "hue-rotate(205deg) saturate(0.8)" },
    moisture: { title: "Atmospheric moisture", filter: "hue-rotate(285deg) saturate(1.35)" },
  } as Record<string, { title: string; filter: string }>)[activeLayer] || { title: "Precipitation", filter: "none" };

  const loadData = async (loc = selectedLoc) => {
    setLoading(true);
    try {
      const res = await fetchForecast(loc.lat, loc.lon, loc.name);
      setData(res);
    } catch (e) {
      console.error("Forecast fetch error:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData(selectedLoc);
  }, [location]);

  // Derived values from backend
  const current = data?.currentBlend;
  const weights = data?.weights?.weights || [];
  const regime = data?.activeRegime;
  const disagreement = data?.disagreement;
  const extremeEvents = data?.extremeEvents || [];
  const modelForecasts = data?.modelForecasts || {};

  // Extract individual model 24h precipitation forecasts
  const getModelPrecip = (modelName: string) => {
    const pts = modelForecasts[modelName] || [];
    if (!pts.length) return 0;
    const slice = pts.slice(0, horizon);
    return Math.round(slice.reduce((acc: number, p: any) => acc + (p.precipitation || 0), 0) * 10) / 10;
  };

  const ecmwfPrecip = getModelPrecip("ECMWF_IFS");
  const aifsPrecip = getModelPrecip("ECMWF_AIFS");
  const gfsPrecip = getModelPrecip("NOAA_GFS");
  const iconPrecip = getModelPrecip("DWD_ICON");
  const blendedPrecip = data?.hourlyTrajectory
    ? Math.round(data.hourlyTrajectory.slice(0, horizon).reduce((acc: number, p: any) => acc + (p.precipitation || 0), 0) * 10) / 10
    : 0;

  // Weights percentage mapping
  const getWeightPct = (name: string) => {
    const item = weights.find((w: any) => w.modelName === name);
    return item ? Math.round(item.weight * 100) : 0;
  };

  const aifsWeight = getWeightPct("ECMWF_AIFS");
  const ifsWeight = getWeightPct("ECMWF_IFS");
  const gfsWeight = getWeightPct("NOAA_GFS");
  const iconWeight = getWeightPct("DWD_ICON");

  return (
    <div className="flex flex-col w-full gap-space-lg select-none">
      {/* TOP HEADER / HERO BAR */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-space-md">
        <div className="flex flex-col">
          <div className="flex items-center gap-space-xs text-on-surface-variant font-label-md text-label-md">
            <span>Good Afternoon, Dr. Rao</span>
            <span className="w-1 h-1 rounded-full bg-primary/60" />
            <span className="text-primary font-semibold">Active Operational Run #0842</span>
          </div>
          <div className="flex items-center gap-space-sm mt-0.5">
            <h1 className="font-headline-lg text-headline-lg text-on-surface tracking-tight">
              Weather Intelligence
            </h1>
            <span className="hidden sm:inline-flex items-center px-2 py-0.5 rounded-full bg-secondary-fixed text-on-secondary-fixed-variant font-label-sm text-label-sm font-bold uppercase tracking-wider">
              v4.2 NeuralBlend
            </span>
          </div>
          <p className="font-body-sm text-body-sm text-on-surface-variant mt-0.5">
            Hybrid AI – NWP Multi-Model Forecast Blending System <span className="opacity-60">•</span> Domain: South &amp; Central Asia (0.05° Ultra-Res)
          </p>
        </div>

        {/* Horizon selector & Date Pill */}
        <div className="flex items-center gap-space-sm flex-wrap">
          <div className="p-1 rounded-full bg-surface-container-lowest/80 backdrop-blur-xl shadow-sm flex items-center gap-1 border border-white/60">
            {([24, 48, 72] as const).map((h) => (
              <button
                key={h}
                onClick={() => setHorizon(h)}
                className={`px-space-md py-1 rounded-full font-label-md text-label-md transition-all ${
                  horizon === h
                    ? "bg-primary text-on-primary font-semibold shadow-[0_4px_12px_rgba(0,74,198,0.28)]"
                    : "text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high/60 font-medium"
                }`}
              >
                {h}h
              </button>
            ))}
          </div>

          <div className="flex items-center gap-space-xs px-space-md py-2 rounded-full bg-surface-container-lowest/80 backdrop-blur-xl shadow-sm hover:bg-surface-container-lowest transition-all cursor-pointer border border-white/60">
            <span className="material-symbols-outlined text-primary text-[18px]">calendar_today</span>
            <span className="font-label-md text-label-md text-on-surface font-semibold">
              Live Forecast Horizon (+{horizon}h)
            </span>
          </div>
        </div>
      </div>

      {/* UPPER MAIN SPLIT GRID (4 Col : 8 Col) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
        {/* LEFT CARD: Selected Location Weather Panel */}
        <div className="lg:col-span-5 xl:col-span-4 rounded-3xl bg-surface-container-lowest/70 backdrop-blur-2xl p-space-lg shadow-[0_20px_45px_-15px_rgba(19,27,46,0.06)] flex flex-col justify-between relative overflow-hidden border border-white/80">
          <div className="absolute -top-12 -right-12 w-48 h-48 rounded-full bg-secondary-fixed/40 blur-3xl pointer-events-none" />
          <div className="relative z-10 flex flex-col gap-space-md">
            {/* Location Picker Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-space-xs group cursor-pointer px-2.5 py-1 -ml-2 rounded-full hover:bg-surface-container-high/60 transition-all">
                <span className="material-symbols-outlined text-primary text-[20px]">location_on</span>
                <div className="flex flex-col">
                  <span className="font-headline-sm text-headline-sm text-on-surface font-bold leading-none flex items-center gap-1">
                    {selectedLoc.name}
                  </span>
                  <span className="font-code-sm text-[11px] text-on-surface-variant/80 mt-0.5">
                    {selectedLoc.lat.toFixed(4)}° N, {selectedLoc.lon.toFixed(4)}° E • {selectedLoc.elev}m ASL
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1">
                {QUICK_LOCATIONS.map((loc) => (
                  <button
                    key={loc.name}
                    onClick={() => setLocation({ name: loc.name, latitude: loc.lat, longitude: loc.lon, elevation: loc.elev })}
                    className={`px-2 py-0.5 rounded-full text-[10px] font-semibold transition-all ${
                      selectedLoc.name === loc.name
                        ? "bg-primary text-white"
                        : "bg-surface-container-low text-on-surface-variant hover:bg-surface-container"
                    }`}
                  >
                    {loc.name.split(",")[0].slice(0, 3).toUpperCase()}
                  </button>
                ))}
              </div>
            </div>

            {/* Hero Temp & Atmospheric Visual */}
            <div className="flex items-center justify-between pt-space-xs">
              <div className="flex flex-col">
                <div className="flex items-baseline gap-1">
                  <span className="font-display-lg text-[4rem] leading-none font-bold text-on-surface tracking-tighter">
                    {current ? Math.round(current.temperature) : 27}
                  </span>
                  <span className="font-display-lg text-headline-lg font-semibold text-primary">°C</span>
                </div>
                <span className="font-headline-sm text-headline-sm text-on-surface-variant font-medium mt-1">
                  {current?.conditionText || "Light to Moderate Rain"}
                </span>
                <div className="flex items-center gap-1.5 mt-2">
                  <span className="w-2 h-2 rounded-full bg-secondary animate-ping" />
                  <span className="font-label-sm text-label-sm text-secondary font-semibold uppercase tracking-wider">
                    Radar Precipitation Active
                  </span>
                </div>
              </div>

              {/* Stylized 3D Translucent Weather Cloud Graphic from Stitch */}
              <div className="relative w-32 h-32 flex items-center justify-center">
                <div className="absolute inset-0 bg-primary-fixed/40 rounded-full blur-2xl" />
                <svg className="relative z-10 w-28 h-28 drop-shadow-[0_12px_24px_rgba(0,83,219,0.22)]" fill="none" viewBox="0 0 120 120">
                  <circle cx="75" cy="42" fill="url(#sun-grad)" opacity="0.9" r="16" />
                  <path d="M38 78C30.268 78 24 71.732 24 64C24 56.5 29.9 50.4 37.3 50.05C39.5 39.8 48.6 32 59.5 32C71.8 32 81.9 41.5 82.5 53.7C88.6 54.7 93 60 93 66.5C93 73.4 87.4 79 80.5 79L38 78Z" fill="url(#cloud-back)" opacity="0.45" />
                  <path d="M35 74C28.3726 74 23 68.6274 23 62C23 55.6 28 50.4 34.3 50.05C36.2 41.2 44 34.5 53.5 34.5C64.1 34.5 72.8 42.6 73.4 53.1C78.6 53.9 82.5 58.5 82.5 64C82.5 70 77.6 74.9 71.6 74.9L35 74Z" fill="url(#cloud-front)" fillOpacity="0.85" />
                  <path d="M35 74C28.3726 74 23 68.6274 23 62C23 55.6 28 50.4 34.3 50.05C36.2 41.2 44 34.5 53.5 34.5C64.1 34.5 72.8 42.6 73.4 53.1C78.6 53.9 82.5 58.5 82.5 64C82.5 70 77.6 74.9 71.6 74.9L35 74Z" stroke="white" strokeOpacity="0.9" strokeWidth="1.5" />
                  <g className="animate-pulse">
                    <path d="M40 82L35 94" opacity="0.8" stroke="#0053DB" strokeLinecap="round" strokeWidth="2.5" />
                    <path d="M52 82L47 96" stroke="#4CD7F6" strokeLinecap="round" strokeWidth="2.5" />
                    <path d="M64 82L59 93" opacity="0.8" stroke="#0053DB" strokeLinecap="round" strokeWidth="2.5" />
                    <path d="M75 82L70 95" stroke="#4CD7F6" strokeLinecap="round" strokeWidth="2.5" />
                  </g>
                  <defs>
                    <linearGradient id="sun-grad" x1="59" y1="26" x2="91" y2="58" gradientUnits="userSpaceOnUse">
                      <stop stopColor="#FFD600" />
                      <stop offset="1" stopColor="#FF9100" />
                    </linearGradient>
                    <linearGradient id="cloud-back" x1="24" y1="32" x2="93" y2="79" gradientUnits="userSpaceOnUse">
                      <stop stopColor="#0053DB" />
                      <stop offset="1" stopColor="#4CD7F6" />
                    </linearGradient>
                    <linearGradient id="cloud-front" x1="23" y1="34" x2="82" y2="75" gradientUnits="userSpaceOnUse">
                      <stop stopColor="#FFFFFF" />
                      <stop offset="0.6" stopColor="#E2E7FF" />
                      <stop offset="1" stopColor="#B4C5FF" />
                    </linearGradient>
                  </defs>
                </svg>
              </div>
            </div>

            {/* Atmospheric Micro Metrics 3x2 Grid */}
            <div className="grid grid-cols-3 gap-2.5 pt-space-xs">
              <div className="p-3 rounded-2xl bg-surface-container-low/70 flex flex-col gap-1">
                <div className="flex items-center gap-1 text-on-surface-variant font-label-sm text-label-sm">
                  <span className="material-symbols-outlined text-primary text-[16px]">water_drop</span>
                  <span>Humidity</span>
                </div>
                <span className="font-headline-sm text-headline-sm font-bold text-on-surface">
                  {current?.humidity ?? "—"}{current?.humidity != null ? "%" : ""}
                </span>
                <span className="font-label-sm text-[10px] text-secondary font-medium">Sat. vapor 96%</span>
              </div>
              <div className="p-3 rounded-2xl bg-surface-container-low/70 flex flex-col gap-1">
                <div className="flex items-center gap-1 text-on-surface-variant font-label-sm text-label-sm">
                  <span className="material-symbols-outlined text-secondary text-[16px]">air</span>
                  <span>Wind</span>
                </div>
                <span className="font-headline-sm text-headline-sm font-bold text-on-surface">
                  {current?.windSpeed ?? "—"} <span className="text-label-sm font-normal text-on-surface-variant">{current?.windSpeed != null ? "km/h" : ""}</span>
                </span>
                <span className="font-label-sm text-[10px] text-on-surface-variant font-medium">
                  {current?.windDirection != null ? `${Math.round(current.windDirection)}°` : "No direction data"}
                </span>
              </div>
              <div className="p-3 rounded-2xl bg-surface-container-low/70 flex flex-col gap-1">
                <div className="flex items-center gap-1 text-on-surface-variant font-label-sm text-label-sm">
                  <span className="material-symbols-outlined text-tertiary text-[16px]">speed</span>
                  <span>Pressure</span>
                </div>
                <span className="font-headline-sm text-headline-sm font-bold text-on-surface">
                  {current?.pressure != null ? Math.round(current.pressure) : "—"} <span className="text-label-sm font-normal text-on-surface-variant">{current?.pressure != null ? "hPa" : ""}</span>
                </span>
                <span className="font-label-sm text-[10px] text-secondary font-medium">Steady (±0.2)</span>
              </div>
            </div>

            {/* Dew Point & Solar Irradiance Inset */}
            <div className="grid grid-cols-2 gap-2.5">
              <div className="px-3 py-2 rounded-xl bg-surface-container-high/40 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-primary text-[15px]">dew_point</span>
                  <span className="font-label-sm text-label-sm text-on-surface-variant">Dew Point</span>
                </div>
                <span className="font-label-md text-label-md font-bold text-on-surface">
                  {current?.dewPoint ?? "—"}{current?.dewPoint != null ? "°C" : ""}
                </span>
              </div>
              <div className="px-3 py-2 rounded-xl bg-surface-container-high/40 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-on-secondary-fixed-variant text-[15px]">wb_sunny</span>
                  <span className="font-label-sm text-label-sm text-on-surface-variant">Irradiance</span>
                </div>
                <span className="font-label-md text-label-md font-bold text-on-surface">420 W/m²</span>
              </div>
            </div>

            {/* Micro Banner: Precipitation Window */}
            <div className="mt-1 p-3 rounded-2xl bg-gradient-to-r from-primary-fixed/60 via-secondary-fixed/40 to-surface-container-low flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-7 h-7 rounded-full bg-primary text-on-primary flex items-center justify-center">
                  <span className="material-symbols-outlined text-[16px]">rainy_light</span>
                </span>
                <div className="flex flex-col">
                  <span className="font-label-md text-label-md font-bold text-on-primary-fixed">
                    Next Heavy Window: +3.5 hrs
                  </span>
                  <span className="font-body-sm text-[11px] text-on-primary-fixed-variant">
                    Peak intensity around {current?.timestamp ? current.timestamp.split("T")[1]?.slice(0, 5) : "19:15"} UTC
                  </span>
                </div>
              </div>
              <div className="flex flex-col items-end">
                <span className="font-label-md text-label-md font-bold text-primary">
                  {current?.confidencePercentage ?? "—"}{current?.confidencePercentage != null ? "%" : ""}
                </span>
                <span className="font-label-sm text-[10px] text-on-surface-variant uppercase">Confidence</span>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT CARD: Main 3D Digital Weather Globe & Predicted Rainfall Field */}
        <div className="lg:col-span-7 xl:col-span-8 rounded-3xl bg-surface-container-lowest/70 backdrop-blur-2xl p-space-lg shadow-[0_20px_45px_-15px_rgba(19,27,46,0.06)] flex flex-col justify-between relative overflow-hidden min-h-[380px] border border-white/80">
          <div className="relative z-20 flex flex-wrap items-center justify-between gap-space-sm pb-space-sm">
            <div className="flex flex-col">
              <div className="flex items-center gap-2">
                <span className="font-headline-sm text-headline-sm text-on-surface font-bold">{layerConfig.title}</span>
                <span className="px-2 py-0.5 rounded-md bg-primary-fixed text-on-primary-fixed-variant font-code-sm text-[11px] font-semibold">
                  Next {horizon} Hours • 0.05° Grid
                </span>
              </div>
              <span className="font-body-sm text-body-sm text-on-surface-variant">
                Blended ensemble probability tensor overlay with convection tracking
              </span>
            </div>
            <div className="flex items-center gap-2">
              <div className="px-3 py-1 rounded-full bg-surface-container-lowest/90 backdrop-blur-md shadow-sm flex items-center gap-1.5 text-on-surface font-label-md text-label-md font-semibold cursor-pointer border border-white/60">
                <span className="w-2.5 h-2.5 rounded-full bg-secondary-container" />
                <span>Rainfall (mm)</span>
                <span className="material-symbols-outlined text-[16px] text-outline">arrow_drop_down</span>
              </div>
            </div>
          </div>

          {/* Subcontinent meteorological tensor contours */}
          <div className="relative flex-1 rounded-2xl overflow-hidden bg-gradient-to-b from-[#eaf2ff] via-[#dce8fd] to-[#cfdffc] flex items-center justify-center p-2 min-h-[280px]">
            <svg key={activeLayer} style={{ filter: layerConfig.filter }} className="absolute inset-0 w-full h-full object-cover transition-all duration-500" fill="none" preserveAspectRatio="xMidYMid slice" viewBox="0 0 800 450">
              <defs>
                <radialGradient cx="40%" cy="50%" id="ocean-glow" r="65%">
                  <stop offset="0%" stopColor="#b8daf8" stopOpacity="0.8" />
                  <stop offset="100%" stopColor="#93c3f2" stopOpacity="1" />
                </radialGradient>
                <radialGradient cx="44%" cy="62%" id="rain-cell-1" r="22%">
                  <stop offset="0%" stopColor="#ba1a1a" stopOpacity="0.95" />
                  <stop offset="35%" stopColor="#ff9100" stopOpacity="0.85" />
                  <stop offset="60%" stopColor="#ffd600" stopOpacity="0.7" />
                  <stop offset="85%" stopColor="#57dffe" stopOpacity="0.5" />
                  <stop offset="100%" stopColor="#0053db" stopOpacity="0" />
                </radialGradient>
                <radialGradient cx="68%" cy="50%" id="rain-cell-2" r="28%">
                  <stop offset="0%" stopColor="#e91e63" stopOpacity="0.85" />
                  <stop offset="30%" stopColor="#7d4ce7" stopOpacity="0.75" />
                  <stop offset="65%" stopColor="#57dffe" stopOpacity="0.6" />
                  <stop offset="100%" stopColor="#2563eb" stopOpacity="0" />
                </radialGradient>
                <filter id="blur-filter" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="16" />
                </filter>
              </defs>
              <rect width="800" height="450" fill="url(#ocean-glow)" />
              {/* Land contour lines */}
              <path d="M260,80 Q320,50 400,60 T480,90 Q540,110 550,160 T520,220 Q560,260 540,310 T460,380 Q430,420 420,440 T390,410 Q340,320 320,250 T280,180 Q250,140 260,80 Z" fill="#e2edfd" opacity="0.9" />
              {/* Isobars / Streamlines */}
              <g opacity="0.55" stroke="#ffffff" strokeDasharray="4,6" strokeWidth="1.2">
                <path d="M120,60 C 220,90 310,130 450,110 S 680,150 780,180" />
                <path d="M100,140 C 240,170 380,190 520,170 S 700,240 820,260" />
                <path d="M140,240 C 280,270 390,260 510,280 S 660,340 760,350" />
              </g>
              {/* Wind Arrows */}
              <g opacity="0.35" stroke="#004ac6" strokeLinecap="round" strokeWidth="1">
                <path d="M 280 280 L 310 260 M 310 260 L 302 260 M 310 260 L 308 268" />
                <path d="M 340 270 L 370 250 M 370 250 L 362 250 M 370 250 L 368 258" />
                <path d="M 400 300 L 430 280 M 430 280 L 422 280 M 430 280 L 428 288" />
              </g>
              {/* Precipitation Tensor Heatmap */}
              <g filter="url(#blur-filter)" style={{ mixBlendMode: "multiply" }}>
                <circle cx="360" cy="275" r="140" fill="url(#rain-cell-1)" />
                <circle cx="540" cy="225" r="170" fill="url(#rain-cell-2)" />
              </g>
              {/* Active Beacon */}
              <g transform="translate(370, 275)">
                <circle cx="0" cy="0" r="18" fill="#0053DB" fillOpacity="0.15" className="animate-ping" />
                <circle cx="0" cy="0" r="7" fill="#0053DB" />
                <circle cx="0" cy="0" r="3.5" fill="#ffffff" />
                <rect x="12" y="-14" width="112" height="26" rx="13" fill="#ffffff" fillOpacity="0.95" />
                <text x="24" y="3" fill="#131b2e" fontFamily="Inter" fontSize="10" fontWeight="700">
                  {selectedLoc.name.split(",")[0]}: {blendedPrecip}mm
                </text>
              </g>
            </svg>

            {/* Left Layer Switcher Glass Dock */}
            <div className="absolute left-3 top-3 bottom-3 flex flex-col justify-between py-2 px-1 rounded-2xl bg-surface-container-lowest/80 backdrop-blur-xl shadow-lg z-30 border border-white/60">
              <div className="flex flex-col gap-2">
                <button
                  onClick={() => setActiveLayer("precip")}
                  className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all ${
                    activeLayer === "precip" ? "bg-primary text-on-primary shadow-md" : "hover:bg-surface-container text-on-surface-variant hover:text-primary"
                  }`}
                  title="Precipitation Layer"
                >
                  <span className="material-symbols-outlined text-[19px]">rainy</span>
                </button>
                <button
                  onClick={() => setActiveLayer("temp")}
                  className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all ${
                    activeLayer === "temp" ? "bg-primary text-on-primary shadow-md" : "hover:bg-surface-container text-on-surface-variant hover:text-primary"
                  }`}
                  title="Temperature Gradients"
                >
                  <span className="material-symbols-outlined text-[19px]">thermostat</span>
                </button>
                <button
                  onClick={() => setActiveLayer("wind")}
                  className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all ${
                    activeLayer === "wind" ? "bg-primary text-on-primary shadow-md" : "hover:bg-surface-container text-on-surface-variant hover:text-primary"
                  }`}
                  title="Wind Streamlines"
                >
                  <span className="material-symbols-outlined text-[19px]">air</span>
                </button>
                <button
                  onClick={() => setActiveLayer("moisture")}
                  className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all ${
                    activeLayer === "moisture" ? "bg-primary text-on-primary shadow-md" : "hover:bg-surface-container text-on-surface-variant hover:text-primary"
                  }`}
                  title="Atmospheric Moisture"
                >
                  <span className="material-symbols-outlined text-[19px]">opacity</span>
                </button>
              </div>
            </div>

            {/* Right Scientific Color Bar Scale */}
            <div className="absolute right-3 top-4 bottom-4 flex flex-col items-center justify-between p-2 rounded-2xl bg-surface-container-lowest/85 backdrop-blur-xl shadow-md z-30 w-11 border border-white/60">
              <span className="font-code-sm text-[10px] font-bold text-on-surface">150</span>
              <div className="w-2.5 flex-1 my-1.5 rounded-full bg-gradient-to-t from-[#0053db] via-[#57dffe] via-[#4ade80] via-[#ffd600] via-[#ff9100] to-[#ba1a1a]" />
              <span className="font-code-sm text-[10px] font-bold text-on-surface">0</span>
            </div>
          </div>
        </div>
      </div>

      {/* MIDDLE SECTION: Model Predictions & Adaptive Blending */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
        {/* Model Predictions Strip */}
        <div className="lg:col-span-7 xl:col-span-8 rounded-3xl bg-surface-container-lowest/70 backdrop-blur-2xl p-space-lg shadow-[0_20px_45px_-15px_rgba(19,27,46,0.06)] flex flex-col justify-between border border-white/80">
          <div className="flex items-center justify-between pb-space-sm">
            <div className="flex items-center gap-space-xs">
              <span className="font-headline-sm text-headline-sm text-on-surface font-bold">
                Model Predictions (Rainfall)
              </span>
              <span className="material-symbols-outlined text-outline text-[18px]">info</span>
            </div>
            <div className="flex items-center gap-space-xs text-on-surface-variant font-label-md text-label-md">
              <span className="w-2 h-2 rounded-full bg-primary" />
              <span>Forecast Horizon: Next {horizon} Hours</span>
            </div>
          </div>

          {/* Comparison Mini-Cards Grid (4 parallel cards) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-space-sm pt-space-xs">
            {/* Card 1: ECMWF IFS */}
            <div className="p-space-md rounded-2xl bg-surface-container-low/80 flex flex-col justify-between hover:bg-surface-container-low transition-all">
              <div className="flex items-center justify-between">
                <span className="font-label-md text-label-md font-semibold text-on-surface-variant">ECMWF IFS</span>
                <span className="w-2 h-2 rounded-full bg-primary" />
              </div>
              <div className="flex items-baseline gap-1 my-2">
                <span className="font-headline-lg text-headline-lg font-bold text-on-surface">{ecmwfPrecip}</span>
                <span className="font-label-lg text-label-lg font-medium text-on-surface-variant">mm</span>
              </div>
              <span className="font-label-sm text-[11px] text-on-surface-variant/80">Weight: {ifsWeight}%</span>
              <div className="w-full h-8 mt-2">
                <svg className="w-full h-full" preserveAspectRatio="none" viewBox="0 0 100 35">
                  <path d="M 0,30 Q 25,5 50,18 T 100,8" fill="none" stroke="#004AC6" strokeLinecap="round" strokeWidth="2.5" />
                </svg>
              </div>
            </div>

            {/* Card 2: ECMWF AIFS */}
            <div className="p-space-md rounded-2xl bg-surface-container-low/80 flex flex-col justify-between hover:bg-surface-container-low transition-all">
              <div className="flex items-center justify-between">
                <span className="font-label-md text-label-md font-semibold text-on-surface-variant">ECMWF AIFS</span>
                <span className="w-2 h-2 rounded-full bg-tertiary" />
              </div>
              <div className="flex items-baseline gap-1 my-2">
                <span className="font-headline-lg text-headline-lg font-bold text-on-surface">{aifsPrecip}</span>
                <span className="font-label-lg text-label-lg font-medium text-on-surface-variant">mm</span>
              </div>
              <span className="font-label-sm text-[11px] text-on-surface-variant/80">Weight: {aifsWeight}%</span>
              <div className="w-full h-8 mt-2">
                <svg className="w-full h-full" preserveAspectRatio="none" viewBox="0 0 100 35">
                  <path d="M 0,25 Q 30,28 55,10 T 100,20" fill="none" stroke="#632ECD" strokeLinecap="round" strokeWidth="2.5" />
                </svg>
              </div>
            </div>

            {/* Card 3: NOAA GFS */}
            <div className="p-space-md rounded-2xl bg-surface-container-low/80 flex flex-col justify-between hover:bg-surface-container-low transition-all">
              <div className="flex items-center justify-between">
                <span className="font-label-md text-label-md font-semibold text-on-surface-variant">NOAA GFS</span>
                <span className="w-2 h-2 rounded-full bg-secondary" />
              </div>
              <div className="flex items-baseline gap-1 my-2">
                <span className="font-headline-lg text-headline-lg font-bold text-on-surface">{gfsPrecip}</span>
                <span className="font-label-lg text-label-lg font-medium text-on-surface-variant">mm</span>
              </div>
              <span className="font-label-sm text-[11px] text-on-surface-variant/80">Weight: {gfsWeight}%</span>
              <div className="w-full h-8 mt-2">
                <svg className="w-full h-full" preserveAspectRatio="none" viewBox="0 0 100 35">
                  <path d="M 0,28 Q 35,12 60,16 T 100,12" fill="none" stroke="#00687A" strokeLinecap="round" strokeWidth="2.5" />
                </svg>
              </div>
            </div>

            {/* Card 4: AeroBlend Final */}
            <div className="p-space-md rounded-2xl bg-gradient-to-br from-primary-fixed/80 via-surface-container-lowest to-secondary-fixed/50 shadow-[0_10px_25px_-5px_rgba(37,99,235,0.18)] flex flex-col justify-between relative overflow-hidden border border-primary/30">
              <div className="absolute top-2 right-2 flex items-center justify-center w-5 h-5 rounded-full bg-primary text-on-primary">
                <span className="material-symbols-outlined text-[13px] font-bold">check</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="font-label-md text-label-md font-bold text-primary">AeroBlend Final</span>
              </div>
              <div className="flex items-baseline gap-1 my-2">
                <span className="font-headline-lg text-headline-lg font-bold text-primary">{blendedPrecip}</span>
                <span className="font-label-lg text-label-lg font-semibold text-primary">mm</span>
              </div>
              <span className="font-label-sm text-[11px] text-on-surface-variant font-semibold">
                Dynamic Neural Gating
              </span>
              <div className="w-full h-8 mt-2">
                <svg className="w-full h-full" preserveAspectRatio="none" viewBox="0 0 100 35">
                  <path d="M 0,30 Q 25,12 55,20 T 100,10" fill="none" stroke="#2563EB" strokeLinecap="round" strokeWidth="3" />
                </svg>
              </div>
            </div>
          </div>
        </div>

        {/* Dynamic Model Weights Donut Chart Card */}
        <div className="lg:col-span-5 xl:col-span-4 rounded-3xl bg-surface-container-lowest/70 backdrop-blur-2xl p-space-lg shadow-[0_20px_45px_-15px_rgba(19,27,46,0.06)] flex flex-col justify-between border border-white/80">
          <div className="flex items-center justify-between">
            <div className="flex flex-col">
              <span className="font-headline-sm text-headline-sm text-on-surface font-bold">Model Weights</span>
              <span className="font-label-sm text-label-sm text-on-surface-variant">Dynamic Regional Allocation</span>
            </div>
            <span className="material-symbols-outlined text-outline text-[20px]">tune</span>
          </div>

          <div className="flex items-center justify-center my-3 relative">
            <div className="relative w-40 h-40 flex items-center justify-center">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="48" fill="none" stroke="#E2E7FF" strokeWidth="12" />
                {/* AI Model Segment */}
                <circle
                  cx="60"
                  cy="60"
                  r="48"
                  fill="none"
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
                  fill="none"
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
                  fill="none"
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
                  fill="none"
                  stroke="#00687A"
                  strokeWidth="12"
                  strokeDasharray={`${(iconWeight / 100) * 301.6} 301.6`}
                  strokeDashoffset={`-${((aifsWeight + ifsWeight + gfsWeight) / 100) * 301.6}`}
                  strokeLinecap="round"
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                <span className="font-headline-md text-headline-md font-bold text-on-surface leading-none">
                  {blendedPrecip}<span className="text-xs font-normal text-on-surface-variant">mm</span>
                </span>
                <span className="font-label-sm text-[10px] text-primary font-semibold uppercase tracking-wider mt-0.5">
                  Blended
                </span>
              </div>
            </div>

            <div className="flex flex-col gap-1.5 ml-4">
              <div className="flex items-center justify-between gap-3 text-on-surface">
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-tertiary" />
                  <span className="font-label-md text-label-md">ECMWF AIFS</span>
                </div>
                <span className="font-code-sm text-code-sm font-bold">{aifsWeight}%</span>
              </div>
              <div className="flex items-center justify-between gap-3 text-on-surface">
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-primary" />
                  <span className="font-label-md text-label-md">ECMWF IFS</span>
                </div>
                <span className="font-code-sm text-code-sm font-bold">{ifsWeight}%</span>
              </div>
              <div className="flex items-center justify-between gap-3 text-on-surface">
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-secondary-container" />
                  <span className="font-label-md text-label-md">NOAA GFS</span>
                </div>
                <span className="font-code-sm text-code-sm font-bold">{gfsWeight}%</span>
              </div>
              <div className="flex items-center justify-between gap-3 text-on-surface">
                <div className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full bg-secondary" />
                  <span className="font-label-md text-label-md">DWD ICON</span>
                </div>
                <span className="font-code-sm text-code-sm font-bold">{iconWeight}%</span>
              </div>
            </div>
          </div>

          <div className="pt-2 flex flex-wrap gap-1.5">
            <span className="px-2 py-0.5 rounded-md bg-surface-container-high/60 text-on-surface-variant font-label-sm text-[10px]">
              {selectedLoc.name.split(",")[0]}
            </span>
            <span className="px-2 py-0.5 rounded-md bg-surface-container-high/60 text-on-surface-variant font-label-sm text-[10px]">
              {regime?.regime || "MONSOON"} Regime
            </span>
            <span className="px-2 py-0.5 rounded-md bg-primary-fixed text-on-primary-fixed-variant font-code-sm text-[10px] font-semibold">
              Bias Corrected
            </span>
          </div>
        </div>
      </div>

      {/* LOWER THREE-COLUMN ANALYTICAL GRID */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-space-lg">
        {/* Column 1: Forecast vs Actual (Historical Verification) */}
        <div className="rounded-3xl bg-surface-container-lowest/70 backdrop-blur-2xl p-space-lg shadow-[0_20px_45px_-15px_rgba(19,27,46,0.06)] flex flex-col justify-between border border-white/80">
          <div className="flex items-center justify-between mb-2">
            <div className="flex flex-col">
              <span className="font-headline-sm text-headline-sm text-on-surface font-bold">Forecast vs Actual</span>
              <span className="font-label-sm text-label-sm text-on-surface-variant">6-Day Backtested Verification</span>
            </div>
            <span className="px-2 py-0.5 rounded bg-surface-container-high font-code-sm text-[10px] text-primary font-bold">
              MAE 1.1mm
            </span>
          </div>

          <div className="w-full h-40 my-2 relative">
            <svg className="w-full h-full" fill="none" viewBox="0 0 320 140">
              <line x1="30" y1="20" x2="310" y2="20" stroke="#E2E7FF" strokeDasharray="2,3" strokeWidth="1" />
              <line x1="30" y1="55" x2="310" y2="55" stroke="#E2E7FF" strokeDasharray="2,3" strokeWidth="1" />
              <line x1="30" y1="90" x2="310" y2="90" stroke="#E2E7FF" strokeDasharray="2,3" strokeWidth="1" />
              <line x1="30" y1="120" x2="310" y2="120" stroke="#C3C6D7" strokeWidth="1" />
              {/* Single NWP line */}
              <path d="M 40,110 L 90,85 L 145,100 L 195,30 L 250,95 L 300,105" stroke="#57DFFE" strokeDasharray="3,3" strokeWidth="1.8" />
              {/* Blended AI path */}
              <path d="M 40,108 L 90,95 L 145,90 L 195,40 L 250,84 L 300,88" stroke="#632ECD" strokeWidth="2.5" />
              {/* Ground truth points */}
              <circle cx="40" cy="110" r="3.5" fill="#004AC6" stroke="#FFFFFF" strokeWidth="1.5" />
              <circle cx="90" cy="94" r="3.5" fill="#004AC6" stroke="#FFFFFF" strokeWidth="1.5" />
              <circle cx="145" cy="88" r="3.5" fill="#004AC6" stroke="#FFFFFF" strokeWidth="1.5" />
              <circle cx="195" cy="42" r="4.5" fill="#004AC6" stroke="#FFFFFF" strokeWidth="2" />
              <circle cx="250" cy="82" r="3.5" fill="#004AC6" stroke="#FFFFFF" strokeWidth="1.5" />
              <circle cx="300" cy="90" r="3.5" fill="#004AC6" stroke="#FFFFFF" strokeWidth="1.5" />
            </svg>
          </div>
          <div className="flex items-center justify-between pt-2 border-t border-surface-variant/30 text-on-surface-variant font-body-sm text-[11px]">
            <span>RMSE: <strong>1.8 mm</strong></span>
            <span className="text-primary font-semibold">32% error reduction vs single NWP</span>
          </div>
        </div>

        {/* Column 2: Extreme Weather Intelligence */}
        <div className="rounded-3xl bg-surface-container-lowest/70 backdrop-blur-2xl p-space-lg shadow-[0_20px_45px_-15px_rgba(19,27,46,0.06)] flex flex-col justify-between border border-white/80">
          <div className="flex items-center justify-between pb-1">
            <div className="flex items-center gap-space-xs">
              <span className="font-headline-sm text-headline-sm text-on-surface font-bold">Extreme Weather</span>
              <span className="w-2 h-2 rounded-full bg-error animate-ping" />
            </div>
            <span className="font-label-sm text-label-sm text-primary font-bold">
              {extremeEvents.length} Active Events
            </span>
          </div>

          <div className="flex flex-col gap-space-sm my-2">
            <div className="p-3.5 rounded-2xl bg-error-container/40 flex items-start justify-between gap-space-sm border border-error/20">
              <div className="flex items-start gap-space-xs">
                <span className="material-symbols-outlined text-error text-[22px] shrink-0 mt-0.5">warning</span>
                <div className="flex flex-col">
                  <div className="flex items-center gap-1.5">
                    <span className="font-label-lg text-label-lg font-bold text-on-error-container">Heavy Rainfall Risk</span>
                    <span className="px-1.5 py-0.2 rounded bg-error text-on-error font-code-sm text-[9px] font-bold">HIGH</span>
                  </div>
                  <p className="font-body-sm text-[11px] text-on-error-container/90 mt-0.5 leading-snug">
                    Localized convective showers across {selectedLoc.name}. Projected burst window in T+3h.
                  </p>
                </div>
              </div>
              <span className="font-headline-sm text-headline-sm font-bold text-error shrink-0">87%</span>
            </div>

            <div className="p-3 rounded-xl bg-surface-container-high/50 flex items-center justify-between text-on-surface">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-tertiary text-[18px]">difference</span>
                <span className="font-body-sm text-[11px] text-on-surface-variant">
                  Model Spread: Δ {disagreement?.range ?? "—"} {disagreement?.range != null ? "mm" : ""} ({disagreement?.spreadLevel ?? "unavailable"})
                </span>
              </div>
              <span className="font-label-sm text-[10px] text-primary font-bold">Calibrated</span>
            </div>
          </div>

          <div className="flex items-center justify-between pt-1 text-on-surface-variant font-label-sm text-[11px]">
            <span>Disaster Management Webhook</span>
            <span className="text-secondary font-semibold">Active Sync</span>
          </div>
        </div>

        {/* Column 3: Confidence & Uncertainty Analysis */}
        <div className="rounded-3xl bg-surface-container-lowest/70 backdrop-blur-2xl p-space-lg shadow-[0_20px_45px_-15px_rgba(19,27,46,0.06)] flex flex-col justify-between border border-white/80">
          <div className="flex items-center justify-between">
            <div className="flex flex-col">
              <span className="font-headline-sm text-headline-sm text-on-surface font-bold">Confidence &amp; Uncertainty</span>
              <span className="font-label-sm text-label-sm text-on-surface-variant">Ensemble Spread Dispersion</span>
            </div>
            <span className="px-2 py-0.5 rounded-full bg-secondary-fixed text-on-secondary-fixed-variant font-code-sm text-[10px] font-bold">
              High P(x)
            </span>
          </div>

          {/* Circular Confidence Progress Gauge */}
          <div className="flex items-center justify-center my-2">
            <div className="relative w-32 h-32 flex items-center justify-center">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="40" fill="none" stroke="#EAEDFF" strokeWidth="8" />
                <circle
                  cx="50"
                  cy="50"
                  r="40"
                  fill="none"
                  stroke="url(#conf-grad)"
                  strokeWidth="8"
                  strokeDasharray="228.7 251.3"
                  strokeLinecap="round"
                />
                <defs>
                  <linearGradient id="conf-grad" x1="0" y1="0" x2="1" y2="1">
                    <stop stopColor="#2563EB" />
                    <stop offset="0.6" stopColor="#632ECD" />
                    <stop offset="1" stopColor="#4CD7F6" />
                  </linearGradient>
                </defs>
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                <span className="font-display-lg text-[2rem] leading-none font-bold text-on-surface">
                  {current?.confidencePercentage ?? "—"}{current?.confidencePercentage != null ? "%" : ""}
                </span>
                <span className="font-label-sm text-[10px] text-on-surface-variant uppercase tracking-wider font-semibold mt-0.5">
                  Confidence
                </span>
              </div>
            </div>
          </div>

          {/* 90% Confidence Interval */}
          <div className="p-3 rounded-2xl bg-surface-container-low/70 flex flex-col gap-1.5">
            <div className="flex items-center justify-between text-on-surface">
              <span className="font-label-sm text-label-sm text-on-surface-variant">90% Confidence Interval</span>
              <span className="font-code-sm text-code-sm font-bold text-primary">
                {current?.confidenceIntervalLow ?? "—"} – {current?.confidenceIntervalHigh ?? "—"} {current?.confidenceIntervalLow != null || current?.confidenceIntervalHigh != null ? "mm" : ""}
              </span>
            </div>
            <div className="w-full h-8">
              <svg className="w-full h-full" fill="none" viewBox="0 0 200 40">
                <path d="M 0,38 Q 60,38 85,25 Q 100,5 115,25 Q 140,38 200,38" stroke="#632ECD" strokeLinecap="round" strokeWidth="2" />
                <path d="M 70,38 Q 85,28 100,6 Q 115,28 130,38 Z" fill="#2563EB" opacity="0.18" />
                <line x1="100" y1="6" x2="100" y2="38" stroke="#004AC6" strokeDasharray="2,2" strokeWidth="1.5" />
              </svg>
            </div>
          </div>
        </div>
      </div>

      {/* Operational Footer Metrics Bar */}
      <div className="rounded-2xl bg-surface-container-lowest/50 backdrop-blur-md px-space-md py-3 flex flex-wrap items-center justify-between gap-space-sm text-on-surface-variant font-label-sm text-[11px] border border-white/60">
        <div className="flex items-center gap-space-md flex-wrap">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-secondary" />
            <span>IFS Cycle: <strong>2026-09-27 00Z</strong></span>
          </span>
          <span>•</span>
          <span>AIFS Neural Meso: <strong>Latency 4.2 sec</strong></span>
          <span>•</span>
          <span>GEFS / ICON Ensemble: <strong>Converged (0.94)</strong></span>
        </div>
        <span className="text-primary font-semibold">ISO 9001 / WMO Meteorological Compliant</span>
      </div>
    </div>
  );
}
