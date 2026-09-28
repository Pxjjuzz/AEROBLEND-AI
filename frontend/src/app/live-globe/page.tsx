"use client";

import { useState, useEffect, useRef } from "react";
import { fetchForecast } from "@/lib/api";
import { useLocation } from "@/components/LocationProvider";

const DATA_LAYERS = [
  { id: "precip", name: "Precipitation Flux", subtitle: "Convective Radar & Rain (mm)", icon: "rainy" },
  { id: "wind", name: "Wind Vector Fields", subtitle: "Particle Streamlines (km/h)", icon: "air" },
  { id: "temp", name: "Surface Thermal", subtitle: "Skin Temp & Heat Index (°C)", icon: "thermostat" },
  { id: "cloud", name: "Cloud Moisture", subtitle: "Optical Infrared Depth", icon: "cloudy_snowing" },
  { id: "weights", name: "Spatial Weight Tensor", subtitle: "Neural vs Physical Dominance", icon: "neurology" },
  { id: "uncertainty", name: "Ensemble Spread (σ)", subtitle: "Stochastic Variance σ-Index", icon: "blur_on" },
];

const TIME_STEPS = ["Now", "+6h", "+12h", "+24h", "+48h", "+72h"];

export default function LiveGlobePage() {
  const { location } = useLocation();
  const cesiumContainerRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<any>(null);
  const layerEntityRef = useRef<any>(null);
  const [activeLayer, setActiveLayer] = useState("precip");
  const [activeAltitude, setActiveAltitude] = useState("10m");
  const [currentTimeStep, setCurrentTimeStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [data, setData] = useState<any>(null);
  const [cesiumReady, setCesiumReady] = useState(false);
  const [hasToken, setHasToken] = useState(false);

  // Fetch forecast data
  useEffect(() => {
    async function load() {
      try {
        const res = await fetchForecast(location.latitude, location.longitude, location.name);
        setData(res);
      } catch (e) {
        console.error("Globe data error:", e);
      }
    }
    load();
  }, [location]);

  // Render an inspection overlay for the currently selected live layer. This
  // makes layer, altitude and timeline controls change the Cesium scene rather
  // than only changing their selected-button styling.
  useEffect(() => {
    const viewer = viewerRef.current;
    const Cesium = typeof window !== "undefined" ? (window as any).Cesium : null;
    if (!viewer || !Cesium) return;
    if (layerEntityRef.current) viewer.entities.remove(layerEntityRef.current);

    const point = data?.hourlyTrajectory?.[currentTimeStep * 6] || data?.currentBlend;
    const values: Record<string, { label: string; value: unknown; unit: string; color: string }> = {
      precip: { label: "Precipitation", value: point?.precipitation, unit: "mm/h", color: "#2563eb" },
      wind: { label: "Wind", value: point?.windSpeed, unit: "km/h", color: "#06b6d4" },
      temp: { label: "Temperature", value: point?.temperature, unit: "°C", color: "#f97316" },
      cloud: { label: "Cloud cover", value: point?.cloudCover, unit: "%", color: "#94a3b8" },
      weights: { label: "Dominant model", value: data?.weights?.dominantModel, unit: "", color: "#7c3aed" },
      uncertainty: { label: "Model spread", value: data?.disagreement?.range, unit: "mm", color: "#e11d48" },
    };
    const layer = values[activeLayer];
    const value = layer?.value ?? "No data";
    layerEntityRef.current = viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(location.longitude, location.latitude, (location.elevation || 0) + 3500),
      point: { pixelSize: 18, color: Cesium.Color.fromCssColorString(layer.color), outlineColor: Cesium.Color.WHITE, outlineWidth: 2, disableDepthTestDistance: Number.POSITIVE_INFINITY },
      label: { text: `${layer.label} @ ${activeAltitude}, ${TIME_STEPS[currentTimeStep]}\n${value}${typeof value === "number" ? ` ${layer.unit}` : ""}`, font: "13px Inter, sans-serif", fillColor: Cesium.Color.WHITE, outlineColor: Cesium.Color.BLACK, outlineWidth: 3, style: Cesium.LabelStyle.FILL_AND_OUTLINE, verticalOrigin: Cesium.VerticalOrigin.BOTTOM, pixelOffset: new Cesium.Cartesian2(0, -22), disableDepthTestDistance: Number.POSITIVE_INFINITY },
    });
    return () => { if (layerEntityRef.current) viewer.entities.remove(layerEntityRef.current); };
  }, [activeLayer, activeAltitude, currentTimeStep, data, location, cesiumReady]);

  // Initialize Cesium JS and Viewer
  useEffect(() => {
    let isMounted = true;

    async function initCesium() {
      if (typeof window === "undefined" || !cesiumContainerRef.current) return;

      // 1. Check for Cesium Ion Token from environment variable
      const token = process.env.NEXT_PUBLIC_CESIUM_ION_TOKEN;
      if (token && token.trim().length > 0) {
        setHasToken(true);
      } else {
        setHasToken(false);
      }

      // 2. Set Cesium base URL
      (window as any).CESIUM_BASE_URL = "https://cesium.com/downloads/cesiumjs/releases/1.120/Build/Cesium/";

      // 3. Load Cesium script if not present
      if (!(window as any).Cesium) {
        await new Promise<void>((resolve, reject) => {
          const script = document.createElement("script");
          script.src = "https://cesium.com/downloads/cesiumjs/releases/1.120/Build/Cesium/Cesium.js";
          script.async = true;
          script.onload = () => resolve();
          script.onerror = (err) => reject(err);
          document.head.appendChild(script);
        });
      }

      if (!isMounted || !cesiumContainerRef.current) return;

      const Cesium = (window as any).Cesium;
      if (!Cesium) return;

      // 4. Configure Cesium.Ion.defaultAccessToken
      if (token && token.trim().length > 0) {
        Cesium.Ion.defaultAccessToken = token.trim();
      }

      // 5. Initialize Cesium Viewer with Cesium Ion World Terrain & Imagery
      try {
        if (viewerRef.current) {
          viewerRef.current.destroy();
          viewerRef.current = null;
        }

        const viewerOptions: any = {
          baseLayerPicker: false,
          geocoder: false,
          animation: false,
          timeline: false,
          fullscreenButton: false,
          vrButton: false,
          homeButton: false,
          infoBox: false,
          sceneModePicker: false,
          selectionIndicator: false,
          navigationHelpButton: false,
        };

        // Attach Real Cesium World Terrain if token is present
        if (token && token.trim().length > 0) {
          try {
            viewerOptions.terrain = Cesium.Terrain.fromWorldTerrain({
              requestWaterMask: true,
              requestVertexNormals: true,
            });
          } catch (terrainErr) {
            console.warn("World Terrain initialization fallback:", terrainErr);
          }
        }

        const viewer = new Cesium.Viewer(cesiumContainerRef.current, viewerOptions);
        viewerRef.current = viewer;

        // Enhance rendering quality
        viewer.scene.globe.enableLighting = true;
        viewer.scene.globe.depthTestAgainstTerrain = true;
        viewer.scene.screenSpaceCameraController.minimumZoomDistance = 500;

        // Fly camera to the selected live location.
        viewer.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(location.longitude, location.latitude, 2500000),
          orientation: {
            heading: Cesium.Math.toRadians(0),
            pitch: Cesium.Math.toRadians(-60),
            roll: 0.0,
          },
          duration: 2.5,
        });

        // Add weather sub-grid observation marker
        viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(location.longitude, location.latitude, location.elevation || 0),
          point: {
            pixelSize: 14,
            color: Cesium.Color.fromCssColorString("#2563eb"),
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 3,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
          label: {
            text: `${location.name} (${location.latitude.toFixed(2)}°N, ${location.longitude.toFixed(2)}°E)`,
            font: "12px Inter, sans-serif",
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            pixelOffset: new Cesium.Cartesian2(0, -16),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });

        setCesiumReady(true);
      } catch (err) {
        console.error("Cesium viewer initialization error:", err);
      }
    }

    initCesium();

    return () => {
      isMounted = false;
      if (viewerRef.current) {
        viewerRef.current.destroy();
        viewerRef.current = null;
      }
    };
  }, [location]);

  // Play/pause loop
  useEffect(() => {
    if (!isPlaying) return;
    const timer = setInterval(() => {
      setCurrentTimeStep((prev) => (prev + 1) % TIME_STEPS.length);
    }, 2000 / speed);
    return () => clearInterval(timer);
  }, [isPlaying, speed]);

  const currentPrecip = data?.currentBlend?.precipitation;
  const currentTemp = data?.currentBlend?.temperature;

  return (
    <div className="flex flex-col w-full relative -mt-4 min-h-[calc(100vh-5.5rem)] select-none">
      <div className="relative w-full h-[calc(100vh-6rem)] rounded-3xl overflow-hidden shadow-2xl bg-surface-container-lowest flex items-center justify-center border border-white/80">
        
        {/* Real Cesium 3D Globe Container */}
        <div ref={cesiumContainerRef} className="absolute inset-0 w-full h-full z-0" />

        {/* Token Status Badge if not configured yet */}
        {!hasToken && (
          <div className="absolute top-24 left-6 z-30 max-w-md p-4 rounded-2xl bg-surface-container-lowest/95 backdrop-blur-xl border border-amber-300 shadow-xl">
            <div className="flex items-start gap-3">
              <span className="material-symbols-outlined text-amber-500 text-[24px]">key</span>
              <div className="flex flex-col gap-1">
                <span className="font-label-lg font-bold text-on-surface">Cesium Ion Token Required</span>
                <p className="font-body-sm text-on-surface-variant text-xs leading-relaxed">
                  Open <code className="bg-surface-container-high px-1.5 py-0.5 rounded font-mono text-[11px] text-primary">frontend/.env.local</code> and paste your token into:
                </p>
                <div className="bg-slate-900 text-slate-100 font-mono text-[11px] p-2 rounded-lg mt-1 select-all">
                  NEXT_PUBLIC_CESIUM_ION_TOKEN=your_token_here
                </div>
                <span className="font-label-sm text-xs text-on-surface-variant mt-1">
                  Then restart your Next.js development server to activate Cesium World Terrain and high-res satellite imagery.
                </span>
              </div>
            </div>
          </div>
        )}

        {/* FLOATING TOP HUD */}
        <div className="absolute top-6 left-6 z-20 flex flex-col gap-space-xs pointer-events-auto">
          <div className="flex items-center gap-space-sm p-space-xs pr-space-md rounded-full bg-surface-container-lowest/80 backdrop-blur-2xl shadow-lg border border-white/60">
            <div className="flex items-center justify-center w-8 h-8 rounded-full bg-primary text-on-primary shadow-sm">
              <span className="material-symbols-outlined text-[18px]">public</span>
            </div>
            <div className="flex flex-col">
              <div className="flex items-center gap-space-xs">
                <span className="font-headline-sm text-headline-sm text-on-surface font-bold tracking-tight">
                  Cesium 3D Digital Twin Globe
                </span>
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-label-sm text-label-sm font-semibold ${
                  hasToken ? "bg-secondary-fixed text-on-secondary-fixed-variant" : "bg-amber-100 text-amber-800"
                }`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${hasToken ? "bg-secondary animate-ping" : "bg-amber-600"}`} />
                  {hasToken ? "Cesium Ion Active" : "Waiting for Token"}
                </span>
              </div>
              <span className="font-body-sm text-body-sm text-on-surface-variant">
                ECMWF IFS + AIFS Neural + NOAA GFS + DWD ICON
              </span>
            </div>
          </div>

          <div className="flex items-center gap-space-md px-space-md py-1.5 rounded-xl bg-surface-container-lowest/60 backdrop-blur-xl shadow-sm border border-white/50 text-on-surface-variant font-code-sm text-code-sm">
            <div className="flex items-center gap-1.5">
              <span className="material-symbols-outlined text-primary text-[15px]">near_me</span>
              <span>{location.latitude.toFixed(4)}° N, {location.longitude.toFixed(4)}° E</span>
            </div>
            <div className="h-3 w-px bg-outline-variant/60" />
            <div className="flex items-center gap-1.5">
              <span className="material-symbols-outlined text-secondary text-[15px]">altitude</span>
              <span>Alt: 840 km</span>
            </div>
            <div className="h-3 w-px bg-outline-variant/60" />
            <div className="flex items-center gap-1.5">
              <span className="material-symbols-outlined text-tertiary text-[15px]">terrain</span>
              <span>Cesium World Terrain</span>
            </div>
          </div>
        </div>

        {/* FLOATING INSPECTION PINNED ANCHOR */}
        <div className="absolute z-20 pointer-events-auto transform -translate-x-1/2 -translate-y-full" style={{ top: "45%", left: "50%" }}>
          <div className="relative mb-3 w-72 rounded-2xl bg-surface-container-lowest/85 backdrop-blur-2xl p-space-md shadow-xl border border-white/80">
            <div className="flex items-start justify-between gap-space-xs">
              <div>
                <div className="flex items-center gap-1 text-primary">
                  <span className="material-symbols-outlined text-[16px]">location_on</span>
                  <span className="font-label-sm text-label-sm font-bold uppercase tracking-wider">Sub-Grid Centroid</span>
                </div>
                <h4 className="font-headline-sm text-headline-sm text-on-surface font-bold">{location.name}</h4>
              </div>
              <span className="px-2 py-0.5 rounded-full bg-primary-fixed text-on-primary-fixed font-code-sm text-code-sm font-bold">
                93% Blend
              </span>
            </div>

            <div className="grid grid-cols-2 gap-space-xs mt-space-sm pt-space-xs border-t border-surface-variant/40 font-body-sm text-body-sm">
              <div className="flex flex-col">
                <span className="text-on-surface-variant font-label-sm text-label-sm">Precip Flux</span>
                <span className="font-headline-sm text-headline-sm text-primary font-bold">{currentPrecip ?? "—"}{currentPrecip != null ? " mm" : ""}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-on-surface-variant font-label-sm text-label-sm">Thermal</span>
                <span className="font-headline-sm text-headline-sm text-on-surface font-bold">{currentTemp ?? "—"}{currentTemp != null ? "°C" : ""}</span>
              </div>
              <div className="flex flex-col mt-1">
                <span className="text-on-surface-variant font-label-sm text-label-sm">Wind Field</span>
                <span className="font-label-md text-label-md text-on-surface font-semibold">14 km/h WSW</span>
              </div>
              <div className="flex flex-col mt-1">
                <span className="text-on-surface-variant font-label-sm text-label-sm">Peak Burst</span>
                <span className="font-label-md text-label-md text-error font-semibold">+4.5h window</span>
              </div>
            </div>
          </div>
        </div>

        {/* FLOATING RIGHT CONTROL STACK: Atmospheric Physics & Layer Selection */}
        <div className="absolute top-6 right-6 z-20 w-80 flex flex-col gap-space-sm pointer-events-auto max-h-[calc(100vh-9.5rem)] overflow-y-auto pr-1">
          <div className="rounded-2xl bg-surface-container-lowest/80 backdrop-blur-2xl p-space-md shadow-xl border border-white/70 flex flex-col gap-space-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-space-xs">
                <span className="material-symbols-outlined text-primary text-[20px]">layers</span>
                <span className="font-label-lg text-label-lg font-bold text-on-surface">Data Layers</span>
              </div>
              <span className="font-code-sm text-[11px] px-2 py-0.5 rounded-full bg-surface-container-high text-on-surface-variant font-semibold">
                6 Real-Time
              </span>
            </div>

            <div className="flex flex-col gap-1.5 mt-1">
              {DATA_LAYERS.map((layer) => {
                const isActive = activeLayer === layer.id;
                return (
                  <button
                    key={layer.id}
                    onClick={() => setActiveLayer(layer.id)}
                    className={`w-full flex items-center justify-between p-2 rounded-xl text-left transition-all group ${
                      isActive
                        ? "bg-surface-container-lowest text-primary shadow-sm border border-primary/20"
                        : "bg-surface-container-low/40 hover:bg-surface-container-lowest/80 text-on-surface"
                    }`}
                  >
                    <div className="flex items-center gap-space-sm">
                      <span className={`material-symbols-outlined text-[19px] ${isActive ? "text-primary" : "text-outline group-hover:text-primary"}`}>
                        {layer.icon}
                      </span>
                      <div className="flex flex-col">
                        <span className="font-label-md text-label-md font-bold text-on-surface">{layer.name}</span>
                        <span className="font-body-sm text-[11px] text-on-surface-variant">{layer.subtitle}</span>
                      </div>
                    </div>
                    {isActive ? (
                      <span className="material-symbols-outlined text-primary text-[18px]">check_circle</span>
                    ) : (
                      <span className="material-symbols-outlined text-outline-variant text-[18px] opacity-0 group-hover:opacity-100">
                        radio_button_unchecked
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {/* Altitude Selector */}
            <div className="mt-2 pt-space-xs border-t border-surface-variant/40 flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <span className="font-label-sm text-label-sm font-semibold text-on-surface-variant uppercase tracking-wider">
                  Barometric Altitude
                </span>
                <span className="font-code-sm text-code-sm text-primary font-bold">{activeAltitude}</span>
              </div>
              <div className="grid grid-cols-4 gap-1 p-1 rounded-xl bg-surface-container-low/80 backdrop-blur-md">
                {["10m", "850hPa", "500hPa", "250hPa"].map((lvl) => (
                  <button
                    key={lvl}
                    onClick={() => setActiveAltitude(lvl)}
                    className={`py-1 text-center font-code-sm text-[11px] rounded-lg transition-all ${
                      activeAltitude === lvl
                        ? "bg-primary text-on-primary font-bold shadow-sm"
                        : "text-on-surface-variant hover:text-on-surface"
                    }`}
                  >
                    {lvl}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* FLOATING BOTTOM TIMELINE CONTROLLER */}
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-20 flex items-center gap-4 px-6 py-3 rounded-full bg-surface-container-lowest/85 backdrop-blur-2xl shadow-xl border border-white/80">
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className="w-10 h-10 rounded-full bg-primary text-white flex items-center justify-center shadow-md hover:bg-primary/90 transition-all"
            title={isPlaying ? "Pause" : "Play"}
          >
            <span className="material-symbols-outlined text-[20px]">
              {isPlaying ? "pause" : "play_arrow"}
            </span>
          </button>

          <div className="flex items-center gap-2">
            {TIME_STEPS.map((step, idx) => (
              <button
                key={step}
                onClick={() => setCurrentTimeStep(idx)}
                className={`px-3 py-1 rounded-full text-xs font-semibold transition-all ${
                  currentTimeStep === idx
                    ? "bg-primary text-white shadow-sm"
                    : "bg-surface-container-low text-on-surface-variant hover:text-on-surface"
                }`}
              >
                {step}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1 border-l border-surface-variant/50 pl-3">
            {[1, 2, 4].map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                className={`w-6 h-6 rounded text-[10px] font-bold transition-all ${
                  speed === s ? "bg-secondary text-white" : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                {s}x
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
