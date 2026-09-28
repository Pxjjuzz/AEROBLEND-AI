"use client";

import { useState } from "react";

export default function AlertsPage() {
  const [rainThreshold, setRainThreshold] = useState(35);
  const [windThreshold, setWindThreshold] = useState(45);
  const [disagreementThreshold, setDisagreementThreshold] = useState(6);
  const [webhookUrl, setWebhookUrl] = useState("https://api.aeroblend.internal/webhook/disaster-response");
  const [saved, setSaved] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  return (
    <div className="flex flex-col w-full gap-space-lg select-none max-w-4xl">
      <div>
        <div className="flex items-center gap-space-xs text-primary font-code-sm text-code-sm uppercase font-bold tracking-widest">
          <span>Early Warning Automation</span>
        </div>
        <h1 className="font-headline-lg text-headline-lg text-on-surface tracking-tight mt-0.5">
          Forecast-Driven Alerts &amp; Triggers
        </h1>
        <p className="font-body-md text-body-md text-on-surface-variant">
          Configure real-time automated alerting rules triggered by blended precipitation, sustained surface winds, or critical inter-model disagreement.
        </p>
      </div>

      {saved && (
        <div className="p-4 rounded-2xl bg-secondary-fixed text-on-secondary-fixed-variant font-label-md text-label-md flex items-center gap-2">
          <span className="material-symbols-outlined text-[20px]">check_circle</span>
          <span>Alert rules updated and synced to operational dispatch worker!</span>
        </div>
      )}

      <form onSubmit={handleSave} className="rounded-3xl bg-surface-container-lowest/80 backdrop-blur-xl p-space-lg shadow-xl border border-white/80 flex flex-col gap-6">
        {/* Rainfall Threshold Slider */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <label className="font-label-lg text-label-lg font-bold text-on-surface flex items-center gap-2">
              <span className="material-symbols-outlined text-primary text-[20px]">rainy</span>
              Heavy Rainfall Threshold (mm/24h)
            </label>
            <span className="font-code-sm text-code-sm font-bold text-primary px-3 py-1 rounded-full bg-primary-fixed">
              {rainThreshold} mm
            </span>
          </div>
          <input
            type="range"
            min={10}
            max={100}
            step={5}
            value={rainThreshold}
            onChange={(e) => setRainThreshold(Number(e.target.value))}
            className="w-full h-2 bg-surface-container rounded-lg appearance-none cursor-pointer accent-primary"
          />
          <span className="font-body-sm text-[11px] text-on-surface-variant">
            Dispatches automated alerts if blended 24h accumulation exceeds this threshold.
          </span>
        </div>

        {/* Wind Speed Threshold Slider */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <label className="font-label-lg text-label-lg font-bold text-on-surface flex items-center gap-2">
              <span className="material-symbols-outlined text-secondary text-[20px]">air</span>
              Sustained Wind Speed Threshold (km/h)
            </label>
            <span className="font-code-sm text-code-sm font-bold text-secondary px-3 py-1 rounded-full bg-secondary-fixed">
              {windThreshold} km/h
            </span>
          </div>
          <input
            type="range"
            min={20}
            max={100}
            step={5}
            value={windThreshold}
            onChange={(e) => setWindThreshold(Number(e.target.value))}
            className="w-full h-2 bg-surface-container rounded-lg appearance-none cursor-pointer accent-secondary"
          />
        </div>

        {/* Inter-Model Disagreement Trigger */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <label className="font-label-lg text-label-lg font-bold text-on-surface flex items-center gap-2">
              <span className="material-symbols-outlined text-tertiary text-[20px]">difference</span>
              Model Disagreement Dispersion Trigger (Spread Δ mm)
            </label>
            <span className="font-code-sm text-code-sm font-bold text-tertiary px-3 py-1 rounded-full bg-tertiary-fixed">
              {disagreementThreshold} mm
            </span>
          </div>
          <input
            type="range"
            min={2}
            max={20}
            step={1}
            value={disagreementThreshold}
            onChange={(e) => setDisagreementThreshold(Number(e.target.value))}
            className="w-full h-2 bg-surface-container rounded-lg appearance-none cursor-pointer accent-tertiary"
          />
        </div>

        {/* Webhook Endpoint */}
        <div className="flex flex-col gap-2">
          <label className="font-label-lg text-label-lg font-bold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-outline text-[20px]">webhook</span>
            Emergency Management Webhook URL
          </label>
          <input
            type="url"
            value={webhookUrl}
            onChange={(e) => setWebhookUrl(e.target.value)}
            className="w-full px-4 py-2.5 rounded-xl bg-surface-container-low text-on-surface font-code-sm text-sm border border-surface-variant/40 focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
        </div>

        <button
          type="submit"
          className="self-start px-6 py-2.5 rounded-full bg-primary text-white font-label-md text-label-md font-bold shadow-md hover:bg-primary/90 transition-all flex items-center gap-2"
        >
          <span className="material-symbols-outlined text-[18px]">save</span>
          <span>Save Alert Rules</span>
        </button>
      </form>
    </div>
  );
}
