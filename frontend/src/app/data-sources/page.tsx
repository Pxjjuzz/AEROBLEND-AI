"use client";

import { useState, useEffect } from "react";
import { fetchProviderHealth, fetchDbHealth, fetchMlHealth } from "@/lib/api";

export default function DataSourcesPage() {
  const [providers, setProviders] = useState<any[]>([]);
  const [dbHealth, setDbHealth] = useState<any>(null);
  const [mlHealth, setMlHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const loadStatus = async () => {
    setLoading(true);
    try {
      const pRes = await fetchProviderHealth();
      setProviders(pRes.providers || []);
      const dRes = await fetchDbHealth();
      setDbHealth(dRes);
      const mRes = await fetchMlHealth();
      setMlHealth(mRes);
    } catch (e) {
      console.error("Health check error:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  return (
    <div className="flex flex-col w-full gap-space-lg select-none">
      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-space-md">
        <div>
          <div className="flex items-center gap-space-xs text-primary font-code-sm text-code-sm uppercase font-bold tracking-widest">
            <span>Operational Upstream Ingestion</span>
          </div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface tracking-tight mt-0.5">
            Data Sources &amp; Health Checks
          </h1>
          <p className="font-body-md text-body-md text-on-surface-variant">
            Live telemetry, API response latencies, and ingestion pipelines across ECMWF, NOAA, DWD, and local persistence.
          </p>
        </div>

        <button
          onClick={loadStatus}
          className="flex items-center gap-2 px-4 py-2 rounded-full bg-surface-container-lowest text-on-surface hover:bg-surface-container shadow-sm border border-white/60 transition-all font-label-md text-label-md"
        >
          <span className="material-symbols-outlined text-[18px] text-primary">refresh</span>
          <span>Refresh Health Probe</span>
        </button>
      </div>

      {/* Core Infrastructure Health Banner */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-space-md">
        <div className="p-4 rounded-2xl bg-surface-container-lowest/80 backdrop-blur-xl shadow-sm border border-white/80 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
              <span className="material-symbols-outlined text-[22px]">database</span>
            </span>
            <div className="flex flex-col">
              <span className="font-label-sm text-label-sm text-on-surface-variant">Database Engine</span>
              <span className="font-headline-sm text-headline-sm font-bold text-on-surface">
                {dbHealth?.status || "CHECKING..."}
              </span>
            </div>
          </div>
          <span className="w-2.5 h-2.5 rounded-full bg-secondary animate-pulse" />
        </div>

        <div className="p-4 rounded-2xl bg-surface-container-lowest/80 backdrop-blur-xl shadow-sm border border-white/80 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="w-10 h-10 rounded-xl bg-tertiary/10 text-tertiary flex items-center justify-center">
              <span className="material-symbols-outlined text-[22px]">neurology</span>
            </span>
            <div className="flex flex-col">
              <span className="font-label-sm text-label-sm text-on-surface-variant">PyTorch Gating Network</span>
              <span className="font-headline-sm text-headline-sm font-bold text-tertiary">
                {mlHealth?.status || "CHECKING..."}
              </span>
            </div>
          </div>
          <span className="w-2.5 h-2.5 rounded-full bg-tertiary animate-pulse" />
        </div>

        <div className="p-4 rounded-2xl bg-surface-container-lowest/80 backdrop-blur-xl shadow-sm border border-white/80 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="w-10 h-10 rounded-xl bg-secondary/10 text-secondary flex items-center justify-center">
              <span className="material-symbols-outlined text-[22px]">cloud_sync</span>
            </span>
            <div className="flex flex-col">
              <span className="font-label-sm text-label-sm text-on-surface-variant">NWP Streams</span>
              <span className="font-headline-sm text-headline-sm font-bold text-on-surface">
                4 Active Models
              </span>
            </div>
          </div>
          <span className="w-2.5 h-2.5 rounded-full bg-secondary" />
        </div>
      </div>

      {/* Provider Details Table */}
      <div className="rounded-3xl bg-surface-container-lowest/80 backdrop-blur-xl p-space-lg shadow-xl border border-white/80">
        <h2 className="font-headline-sm text-headline-sm text-on-surface font-bold mb-4">
          Live Model Streams &amp; Upstream Latencies
        </h2>
        <div className="overflow-x-auto w-full">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-surface-container-low/60 rounded-xl font-label-sm text-label-sm text-on-surface-variant uppercase">
                <th className="py-3 px-4 rounded-l-xl">Source / Provider</th>
                <th className="py-3 px-4">Model Core</th>
                <th className="py-3 px-4">Live Latency</th>
                <th className="py-3 px-4">Resolution</th>
                <th className="py-3 px-4">Update Cadence</th>
                <th className="py-3 px-4 rounded-r-xl">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-variant/30 font-body-sm text-body-sm">
              {providers.map((p, idx) => (
                <tr key={idx} className="hover:bg-surface-container-high/40 transition-colors">
                  <td className="py-3.5 px-4 font-bold text-on-surface">{p.provider}</td>
                  <td className="py-3.5 px-4 text-primary font-semibold">{p.model}</td>
                  <td className="py-3.5 px-4 font-code-sm text-code-sm font-bold text-secondary">
                    {p.latencyMs} ms
                  </td>
                  <td className="py-3.5 px-4 text-on-surface-variant font-code-sm text-code-sm">{p.resolution}</td>
                  <td className="py-3.5 px-4 text-on-surface-variant">{p.updateFrequency}</td>
                  <td className="py-3.5 px-4">
                    <span className="px-2.5 py-0.5 rounded-full bg-secondary-fixed text-on-secondary-fixed-variant font-code-sm text-[10px] font-bold">
                      {p.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
