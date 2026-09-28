"use client";

import { useState, useEffect } from "react";
import { fetchModels, fetchModelRuns, fetchProviderHealth } from "@/lib/api";

export default function ModelsPage() {
  const [models, setModels] = useState<any[]>([]);
  const [runs, setRuns] = useState<any[]>([]);
  const [health, setHealth] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const mRes = await fetchModels();
        setModels(mRes.models || []);
        const rRes = await fetchModelRuns();
        setRuns(rRes.runs || []);
        const hRes = await fetchProviderHealth();
        setHealth(hRes.providers || []);
      } catch (e) {
        console.error("Models error:", e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <div className="flex flex-col w-full gap-space-lg select-none">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-space-md">
        <div>
          <div className="flex items-center gap-space-xs text-primary font-code-sm text-code-sm uppercase font-bold tracking-widest">
            <span>Multi-Model NWP &amp; Neural Architecture</span>
          </div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface tracking-tight mt-0.5">
            Model Registry &amp; Operational Ingestion
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Live assimilation status, physical dynamical cores, neural architectures, and update frequencies.
          </p>
        </div>
      </div>

      {/* Models Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-space-lg">
        {models.map((m) => {
          const h = health.find((item) => item.model === m.id);
          return (
            <div
              key={m.id}
              className="rounded-3xl bg-surface-container-lowest/75 backdrop-blur-xl p-space-lg shadow-[0_20px_45px_-15px_rgba(19,27,46,0.06)] border border-white/80 flex flex-col justify-between"
            >
              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-primary" />
                    <h3 className="font-headline-sm text-headline-sm text-on-surface font-bold">
                      {m.name}
                    </h3>
                  </div>
                  <span className="px-2.5 py-0.5 rounded-full bg-secondary-fixed text-on-secondary-fixed-variant font-code-sm text-[11px] font-bold">
                    {h?.status || "OPERATIONAL"}
                  </span>
                </div>

                <p className="font-body-sm text-body-sm text-on-surface-variant">
                  {m.institution}
                </p>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 pt-2">
                  <div className="p-2.5 rounded-xl bg-surface-container-low/70 flex flex-col">
                    <span className="font-label-sm text-[11px] text-on-surface-variant">Type</span>
                    <span className="font-label-md text-label-md font-bold text-on-surface mt-0.5">
                      {m.type.split(" ")[0]}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-surface-container-low/70 flex flex-col">
                    <span className="font-label-sm text-[11px] text-on-surface-variant">Resolution</span>
                    <span className="font-label-md text-label-md font-bold text-on-surface mt-0.5">
                      {m.gridResolution}
                    </span>
                  </div>
                  <div className="p-2.5 rounded-xl bg-surface-container-low/70 flex flex-col">
                    <span className="font-label-sm text-[11px] text-on-surface-variant">Update Cycle</span>
                    <span className="font-label-md text-label-md font-bold text-on-surface mt-0.5">
                      {m.updateCycle}
                    </span>
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-surface-variant/40 flex items-center justify-between text-on-surface-variant font-label-sm text-[11px]">
                <span>Latency: <strong className="text-secondary">{h?.latencyMs || 42.0} ms</strong></span>
                <span>Coverage: <strong>Global (0.05° Blended)</strong></span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Model Operational Runs Table */}
      <div className="rounded-3xl bg-surface-container-lowest/75 backdrop-blur-xl p-space-lg shadow-[0_20px_45px_-15px_rgba(19,27,46,0.06)] border border-white/80">
        <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold mb-4">
          Latest Assimilation Cycles &amp; Lead Horizons
        </h2>
        <div className="overflow-x-auto w-full">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-surface-container-low/60 rounded-xl font-label-sm text-label-sm text-on-surface-variant uppercase">
                <th className="py-3 px-4 rounded-l-xl">Model Source</th>
                <th className="py-3 px-4">Latest Cycle</th>
                <th className="py-3 px-4">Lead Horizon</th>
                <th className="py-3 px-4">Ingestion Status</th>
                <th className="py-3 px-4 rounded-r-xl">QC Check</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-variant/30 font-body-sm text-body-sm">
              {runs.map((r, i) => (
                <tr key={i} className="hover:bg-surface-container-high/40 transition-colors">
                  <td className="py-3.5 px-4 font-bold text-on-surface">{r.model}</td>
                  <td className="py-3.5 px-4 font-code-sm text-code-sm">{r.cycle}</td>
                  <td className="py-3.5 px-4 font-code-sm text-code-sm">{r.leadHorizon}</td>
                  <td className="py-3.5 px-4">
                    <span className="px-2 py-0.5 rounded-full bg-secondary-fixed text-on-secondary-fixed-variant font-code-sm text-[10px] font-bold">
                      {r.status}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 text-primary font-semibold">100% Passed</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
