"use client";

import { useState, useEffect } from "react";
import { fetchVerification } from "@/lib/api";
import { useLocation } from "@/components/LocationProvider";

export default function AnalyticsPage() {
  const { location } = useLocation();
  const [periodDays, setPeriodDays] = useState(30);
  const [variable, setVariable] = useState<"temperature" | "precipitation">("temperature");
  const [report, setReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchVerification(location.name, periodDays, variable, location.latitude, location.longitude);
        setReport(res);
        if (!res?.computed) {
          setError(res?.unavailableReason || "Verification could not be computed for this window.");
        }
      } catch (e) {
        setReport(null);
        setError(e instanceof Error ? e.message : "Verification request failed");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [periodDays, variable, location]);

  // Headline numbers come only from a computed report. Previously these used
  // `report?.overallMae || 1.14`, so any missing or zero value silently
  // rendered a hardcoded constant that looked like a measurement.
  const unit = variable === "precipitation" ? "mm/day" : "°C";
  const fmt = (n: unknown, digits = 2) =>
    report?.computed && typeof n === "number" ? n.toFixed(digits) : "--";
  const byName = (name: string) =>
    (report?.modelComparisons || []).find((m: any) => m.modelName === name);
  const showPct = (n: unknown) =>
    report?.computed && typeof n === "number" ? `${(n * 100).toFixed(1)}%` : "--";

  return (
    <div className="flex flex-col w-full gap-space-lg select-none">
      {/* Top Scientific Bar & Executive Title */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-space-md">
        <div className="flex flex-col">
          <div className="flex items-center gap-space-xs">
            <span className="font-code-sm text-code-sm text-primary uppercase font-bold tracking-widest">
              Scientific Verification Deck
            </span>
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-secondary" />
            <span className="font-label-sm text-label-sm text-on-surface-variant">
              Window: {periodDays} day{periodDays === 1 ? "" : "s"} ending at the
              verification lag
            </span>
          </div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface tracking-tight mt-0.5">
            Forecast Skill &amp; Analytics Benchmark
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Skill is computed against ERA5 reanalysis from the archive, not against
            a station network. ERA5 is itself a model, so these are inter-model
            scores.
          </p>
        </div>

        {/* Action Controls & Time Horizon Selector */}
        <div className="flex items-center gap-space-sm flex-wrap">
          <div className="p-1 rounded-full bg-surface-container-lowest/80 backdrop-blur-xl shadow-sm flex items-center border border-white/60">
            {[
              { label: "7 days", days: 7 },
              { label: "30 days", days: 30 },
              { label: "90 days", days: 90 },
            ].map((p) => (
              <button
                key={p.days}
                onClick={() => setPeriodDays(p.days)}
                className={`px-space-md py-1 rounded-full font-label-md text-label-md transition-all ${
                  periodDays === p.days
                    ? "bg-primary text-on-primary shadow-sm font-semibold"
                    : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="p-1 rounded-full bg-surface-container-lowest/80 backdrop-blur-xl shadow-sm flex items-center border border-white/60">
            {[
              { label: "Temperature", v: "temperature" as const },
              { label: "Rainfall", v: "precipitation" as const },
            ].map((p) => (
              <button
                key={p.v}
                onClick={() => setVariable(p.v)}
                className={`px-space-md py-1 rounded-full font-label-md text-label-md transition-all ${
                  variable === p.v
                    ? "bg-secondary text-on-secondary shadow-sm font-semibold"
                    : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-2xl p-space-md bg-error-container/40 border border-error/30 text-on-error-container font-body-md">
          Verification unavailable: {error}
        </div>
      )}

      {/* 1. KPI Ribbon (Liquid Glass Cards) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-space-md">
        {/* MAE Card */}
        <div className="rounded-2xl p-space-lg bg-surface-container-lowest/70 backdrop-blur-xl shadow-[0_20px_40px_-15px_rgba(15,23,42,0.05)] flex flex-col justify-between relative overflow-hidden group hover:translate-y-[-2px] transition-all border border-white/80">
          <div className="absolute -top-10 -right-10 w-24 h-24 rounded-full bg-primary-fixed/50 blur-2xl pointer-events-none" />
          <div>
            <div className="flex items-center justify-between">
              <span className="font-label-md text-label-md uppercase tracking-wider text-on-surface-variant">
                Mean Absolute Error (MAE)
              </span>
              <span className="px-2 py-0.5 rounded-full bg-secondary-fixed/50 text-on-secondary-fixed-variant font-code-sm text-code-sm font-semibold">
                Inverse-variance blend
              </span>
            </div>
            <div className="flex items-baseline gap-space-xs mt-space-sm">
              <span className="font-display-lg text-display-lg text-on-surface leading-none">
                {fmt(report?.overallMae)}
              </span>
              <span className="font-label-lg text-label-lg text-on-surface-variant">{unit}</span>
            </div>
          </div>
          <div className="mt-space-md pt-space-sm bg-surface-variant/20 rounded-xl px-space-sm py-space-xs flex items-center justify-between">
            <span className="font-label-sm text-label-sm text-on-surface-variant">
              {byName("Persistence")
                ? `Persistence baseline: ${byName("Persistence").mae?.toFixed(3)} ${unit}`
                : "Persistence baseline unavailable"}
            </span>
            <span className="material-symbols-outlined text-secondary text-[18px]">trending_down</span>
          </div>
        </div>

        {/* RMSE Card */}
        <div className="rounded-2xl p-space-lg bg-surface-container-lowest/70 backdrop-blur-xl shadow-[0_20px_40px_-15px_rgba(15,23,42,0.05)] flex flex-col justify-between relative overflow-hidden group hover:translate-y-[-2px] transition-all border border-white/80">
          <div className="absolute -top-10 -right-10 w-24 h-24 rounded-full bg-secondary-fixed/60 blur-2xl pointer-events-none" />
          <div>
            <div className="flex items-center justify-between">
              <span className="font-label-md text-label-md uppercase tracking-wider text-on-surface-variant">
                Root Mean Sq Error (RMSE)
              </span>
              <span className="px-2 py-0.5 rounded-full bg-secondary-fixed/50 text-on-secondary-fixed-variant font-code-sm text-code-sm font-semibold">
                {report?.computed ? `${report?.sampleCount ?? 0} daily means` : "no data"}
              </span>
            </div>
            <div className="flex items-baseline gap-space-xs mt-space-sm">
              <span className="font-display-lg text-display-lg text-on-surface leading-none">
                {fmt(report?.overallRmse)}
              </span>
              <span className="font-label-lg text-label-lg text-on-surface-variant">{unit}</span>
            </div>
          </div>
          <div className="mt-space-md pt-space-sm bg-surface-variant/20 rounded-xl px-space-sm py-space-xs flex items-center justify-between">
            <span className="font-label-sm text-label-sm text-on-surface-variant">
              Aggregated from hourly {variable} series
            </span>
            <span className="material-symbols-outlined text-primary text-[18px]">verified</span>
          </div>
        </div>

        {/* Skill Score */}
        <div className="rounded-2xl p-space-lg bg-surface-container-lowest/70 backdrop-blur-xl shadow-[0_20px_40px_-15px_rgba(15,23,42,0.05)] flex flex-col justify-between relative overflow-hidden group hover:translate-y-[-2px] transition-all border border-white/80">
          <div className="absolute -top-10 -right-10 w-24 h-24 rounded-full bg-tertiary-fixed/60 blur-2xl pointer-events-none" />
          <div>
            <div className="flex items-center justify-between">
              <span className="font-label-md text-label-md uppercase tracking-wider text-on-surface-variant">
                Skill Score vs Persistence
              </span>
              <span className="px-2 py-0.5 rounded-full bg-tertiary-fixed text-on-tertiary-fixed-variant font-code-sm text-code-sm font-semibold">
                {typeof report?.skillScoreVsPersistence === "number" && report.skillScoreVsPersistence < 0
                  ? "Worse than baseline"
                  : "Beats baseline"}
              </span>
            </div>
            <div className="flex items-baseline gap-space-xs mt-space-sm">
              <span className="font-display-lg text-display-lg text-primary leading-none">
                {fmt(report?.skillScoreVsPersistence, 3)}
              </span>
            </div>
          </div>
          <div className="mt-space-md pt-space-sm bg-surface-variant/20 rounded-xl px-space-sm py-space-xs flex items-center justify-between">
            <span className="font-label-sm text-label-sm text-on-surface-variant">
              1.0 means matching the persistence baseline; negative is worse
            </span>
            <span className="material-symbols-outlined text-tertiary text-[18px]">check_circle</span>
          </div>
        </div>

        {/* FAR Extreme Rain */}
        <div className="rounded-2xl p-space-lg bg-surface-container-lowest/70 backdrop-blur-xl shadow-[0_20px_40px_-15px_rgba(15,23,42,0.05)] flex flex-col justify-between relative overflow-hidden group hover:translate-y-[-2px] transition-all border border-white/80">
          <div className="absolute -top-10 -right-10 w-24 h-24 rounded-full bg-error-container/40 blur-2xl pointer-events-none" />
          <div>
            <div className="flex items-center justify-between">
              <span className="font-label-md text-label-md uppercase tracking-wider text-on-surface-variant">
                False Alarm Ratio
              </span>
              <span className="px-2 py-0.5 rounded-full bg-surface-variant text-on-surface font-code-sm text-code-sm font-semibold">
                {report?.computed ? "Reported" : "Unavailable"}
              </span>
            </div>
            <div className="flex items-baseline gap-space-xs mt-space-sm">
              <span className="font-display-lg text-display-lg text-on-surface leading-none">
                {showPct(report?.falseAlarmRatio)}
              </span>
            </div>
          </div>
          <div className="mt-space-md pt-space-sm bg-surface-variant/20 rounded-xl px-space-sm py-space-xs flex items-center justify-between">
            <span className="font-label-sm text-label-sm text-on-surface-variant">
              Needs at least 3 observed events; otherwise reported as unavailable
            </span>
            <span className="material-symbols-outlined text-secondary text-[18px]">shield</span>
          </div>
        </div>
      </div>

      {/* 2. Per-model comparison, rendered from the computed report */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg">
        <div className="lg:col-span-7 rounded-2xl p-space-lg bg-surface-container-lowest/75 backdrop-blur-xl shadow-[0_20px_40px_-15px_rgba(15,23,42,0.05)] flex flex-col justify-between border border-white/80">
          <div>
            <div className="flex items-center gap-space-xs">
              <span className="w-2.5 h-2.5 rounded-full bg-primary" />
              <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold">
                Per-model error vs ERA5 ({unit})
              </h2>
            </div>
            <p className="font-body-sm text-body-sm text-on-surface-variant mt-0.5">
              {report?.evaluationPeriod || "No evaluation period"}
            </p>
          </div>

          {report?.computed && report.modelComparisons?.length ? (
            <div className="w-full mt-space-md flex flex-col gap-space-sm">
              {(() => {
                const worst = Math.max(
                  ...report.modelComparisons.map((m: any) => m.mae || 0),
                  0.000001
                );
                return report.modelComparisons.map((m: any) => (
                  <div key={m.modelName} className="flex flex-col gap-1">
                    <div className="flex items-baseline justify-between">
                      <span className="font-label-md text-label-md text-on-surface">
                        {m.modelName.replace(/_/g, " ")}
                      </span>
                      <span className="font-code-sm text-code-sm text-on-surface-variant">
                        MAE {m.mae?.toFixed(3)} | RMSE {m.rmse?.toFixed(3)} | bias {m.bias?.toFixed(3)}
                      </span>
                    </div>
                    <div className="w-full bg-surface-variant/40 rounded-full h-2 overflow-hidden">
                      <div
                        className={
                          m.modelName === "Inverse_Variance"
                            ? "bg-primary h-full rounded-full"
                            : "bg-secondary-container h-full rounded-full"
                        }
                        style={{ width: `${Math.max(2, ((m.mae || 0) / worst) * 100)}%` }}
                      />
                    </div>
                  </div>
                ));
              })()}
            </div>
          ) : (
            <p className="font-body-sm text-body-sm text-on-surface-variant mt-space-md">
              {loading ? "Loading verification metrics..." : error || "No metrics computed for this window."}
            </p>
          )}
        </div>

        {/* Dynamic Blending Weight Stream (5 Cols) */}
        <div className="lg:col-span-5 rounded-2xl p-space-lg bg-surface-container-lowest/75 backdrop-blur-xl shadow-[0_20px_40px_-15px_rgba(15,23,42,0.05)] flex flex-col justify-between border border-white/80">
          <div>
            <div className="flex items-center justify-between pb-space-sm">
              <div>
                <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold">
                  Dynamic Blending Shift (0h - 120h)
                </h2>
                <p className="font-body-sm text-body-sm text-on-surface-variant mt-0.5">
                  Ensemble weight distribution over forecast lead time
                </p>
              </div>
              <span className="material-symbols-outlined text-primary text-[20px]">tune</span>
            </div>

      {/* Lead-Time Blending Breakdown Visual */}
      {report?.leadTimeDegradation?.length ? (
        <div className="w-full h-56 mt-space-md relative">
          <svg className="w-full h-full overflow-hidden rounded-xl" preserveAspectRatio="none" viewBox="0 0 480 200">
            <defs>
              <linearGradient id="aiWeightGrad" x1="0" x2="1" y1="0" y2="0">
                <stop offset="0%" stopColor="#632ecd" stopOpacity="0.85" />
                <stop offset="100%" stopColor="#7d4ce7" stopOpacity="0.3" />
              </linearGradient>
              <linearGradient id="ensembleWeightGrad" x1="0" x2="1" y1="0" y2="0">
                <stop offset="0%" stopColor="#00687a" stopOpacity="0.5" />
                <stop offset="100%" stopColor="#00687a" stopOpacity="0.85" />
              </linearGradient>
              <linearGradient id="nwpWeightGrad" x1="0" x2="1" y1="0" y2="0">
                <stop offset="0%" stopColor="#2563eb" stopOpacity="0.5" />
                <stop offset="100%" stopColor="#004ac6" stopOpacity="0.75" />
              </linearGradient>
            </defs>
            <path d="M 0 140 C 120 140, 240 120, 480 90 L 480 200 L 0 200 Z" fill="url(#nwpWeightGrad)" />
            <path d="M 0 90 C 120 100, 240 70, 480 25 L 480 90 C 240 120, 120 140, 0 140 Z" fill="url(#ensembleWeightGrad)" />
            <path d="M 0 0 L 480 0 L 480 25 C 240 70, 120 100, 0 90 Z" fill="url(#aiWeightGrad)" />
          </svg>
          <div className="absolute inset-0 flex justify-between items-center px-4 pointer-events-none text-white font-label-sm font-semibold">
            {report.leadTimeDegradation.map((bin: any) => (
              <div key={bin.leadTime} className="flex flex-col">
                <span className="text-[10px] uppercase opacity-80">T+{bin.leadTime}h</span>
                <span className="text-white drop-shadow">
                  {typeof bin.metrics?.mae === "number" ? bin.metrics.mae.toFixed(2) : "--"} {unit}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="w-full h-56 mt-space-md rounded-xl bg-surface-container-high/30 border border-white/50 flex flex-col items-center justify-center text-center px-space-lg">
          <span className="material-symbols-outlined text-on-surface-variant text-[32px]">tune</span>
          <p className="font-body-sm text-body-sm text-on-surface-variant mt-space-xs">
            Lead-time weight degradation is not computed. The verification endpoint
            scores one window at one lead; it does not bin errors by lead time.
          </p>
        </div>
      )}

            <div className="flex justify-between items-center text-outline font-code-sm text-[11px] pt-space-xs px-2">
              <span>+0h (Nowcast)</span>
              <span>+24h</span>
              <span>+48h</span>
              <span>+72h</span>
              <span>+120h (Synoptic)</span>
            </div>

      <div className="mt-space-md p-space-sm rounded-xl bg-surface-container-high/40 flex items-start gap-space-sm border border-white/50">
        <span className="material-symbols-outlined text-primary text-[20px] shrink-0 mt-0.5">info</span>
        <p className="font-body-sm text-body-sm text-on-surface">
          <strong className="font-semibold text-primary">Scope:</strong> scores below are
          inter-model, measured against ERA5 reanalysis on daily means. The archive
          indexes models by valid time and does not expose run initialisation, so they
          are not restricted to a single forecast lead.
        </p>
      </div>
          </div>
        </div>
      </div>

      {/* 3. Regional Error Decomposition Matrix */}
      <div className="w-full rounded-2xl p-space-lg bg-surface-container-lowest/70 backdrop-blur-xl shadow-[0_20px_40px_-15px_rgba(15,23,42,0.05)] border border-white/80">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm pb-space-md">
          <div>
            <div className="flex items-center gap-space-xs">
              <span className="material-symbols-outlined text-primary text-[20px]">terrain</span>
              <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold">
                Regional &amp; Regime Error Decomposition Matrix
              </h2>
            </div>
        <p className="font-body-sm text-body-sm text-on-surface-variant mt-0.5">
          Decomposition by climatic zone and dominant circulation pattern
        </p>
      </div>
      <span className="px-space-sm py-1 rounded-full bg-surface-container-high font-code-sm text-code-sm text-on-surface-variant">
        {report?.computed ? `${report.sampleCount} daily means, single grid cell` : "No data"}
      </span>
    </div>

        <div className="overflow-x-auto w-full">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-surface-container-low/60 rounded-xl">
                <th className="py-space-sm px-space-md font-label-md text-label-md text-on-surface-variant rounded-l-xl">Climatic Zone / Terrain</th>
                <th className="py-space-sm px-space-md font-label-md text-label-md text-on-surface-variant">Dominant Regime</th>
                <th className="py-space-sm px-space-md font-label-md text-label-md text-on-surface-variant">Raw NWP MAE</th>
                <th className="py-space-sm px-space-md font-label-md text-label-md text-on-surface-variant text-primary font-bold">Inverse-Variance MAE</th>
                <th className="py-space-sm px-space-md font-label-md text-label-md text-on-surface-variant">Skill Delta</th>
                <th className="py-space-sm px-space-md font-label-md text-label-md text-on-surface-variant rounded-r-xl">Confidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-variant/30">
              {report?.regionalMatrix?.map((row: any, idx: number) => (
                <tr key={idx} className="hover:bg-surface-container-high/40 transition-colors">
                  <td className="py-space-md px-space-md font-label-lg text-label-lg text-on-surface flex items-center gap-space-xs">
                    <span className="w-2 h-2 rounded-full bg-secondary" />
                    {row.zone}
                  </td>
                  <td className="py-space-md px-space-md font-body-sm text-body-sm text-on-surface-variant">
                    {row.regime}
                  </td>
                  <td className="py-space-md px-space-md font-code-sm text-code-sm text-outline">
                    {row.rawNwpMae} mm
                  </td>
                  <td className="py-space-md px-space-md font-code-sm text-code-sm text-primary font-bold">
                    {row.aeroBlendMae} mm
                  </td>
                  <td className="py-space-md px-space-md font-code-sm text-code-sm text-secondary font-bold">
                    {row.skillDelta}
                  </td>
                  <td className="py-space-md px-space-md">
                    <div className="w-24 bg-surface-variant/40 rounded-full h-2 overflow-hidden">
                      <div className="bg-secondary h-full rounded-full" style={{ width: `${row.confidence}%` }} />
                    </div>
                  </td>
            </tr>
          ))}
        </tbody>
      </table>
      {(!report?.regionalMatrix || report.regionalMatrix.length === 0) && (
        <p className="font-body-sm text-body-sm text-on-surface-variant px-space-md py-space-lg text-center">
          Regional decomposition is not computed. The verification endpoint scores a
          single grid cell against ERA5 and does not evaluate multiple climate zones.
        </p>
      )}
        </div>
      </div>
    </div>
  );
}
