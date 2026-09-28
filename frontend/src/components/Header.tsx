"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { searchLocations, type LocationChoice } from "@/lib/api";
import { useLocation } from "@/components/LocationProvider";

export default function Header() {
  const router = useRouter();
  const { setLocation } = useLocation();
  const [currentTime, setCurrentTime] = useState("");
  const [searchVal, setSearchVal] = useState("");
  const [matches, setMatches] = useState<LocationChoice[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const options: Intl.DateTimeFormatOptions = {
        weekday: "short",
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "UTC",
      };
      setCurrentTime(`${now.toLocaleDateString("en-GB", options)} UTC`);
    };
    updateTime();
    const interval = setInterval(updateTime, 60000);
    return () => clearInterval(interval);
  }, []);

  const chooseLocation = (match: LocationChoice) => {
    setLocation(match);
    setSearchVal("");
    setMatches([]);
    router.push("/");
  };
  const runSearch = async () => {
    const query = searchVal.trim();
    if (query.length < 2) return;
    setSearching(true); setSearchError("");
    try {
      const results = await searchLocations(query);
      setMatches(results);
      if (!results.length) setSearchError("No matching location found.");
    } catch { setSearchError("Location search is unavailable. Try again shortly."); }
    finally { setSearching(false); }
  };
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") void runSearch();
    if (e.key === "Escape") setMatches([]);
  };

  useEffect(() => {
    const query = searchVal.trim();
    if (query.length < 2) { setMatches([]); setSearchError(""); return; }
    const timer = window.setTimeout(() => void runSearch(), 280);
    return () => window.clearTimeout(timer);
  }, [searchVal]);

  return (
    <header className="fixed top-0 left-64 right-0 h-16 z-40 px-space-lg flex items-center justify-between bg-surface/75 backdrop-blur-xl shadow-[0_1px_8px_rgba(0,0,0,0.04)] border-b border-surface-variant/30">
      {/* Search Bar */}
      <div className="flex items-center gap-space-md flex-1 max-w-xl">
        <div className="relative w-full flex items-center">
          <button type="button" onClick={() => void runSearch()} aria-label="Search locations" className="material-symbols-outlined absolute left-3 text-outline text-[18px] hover:text-primary">
            search
          </button>
          <input
            className="w-full pl-9 pr-14 py-2 bg-surface-container-lowest/80 text-on-surface placeholder:text-on-surface-variant/70 font-body-sm text-body-sm rounded-full focus:outline-none focus:ring-2 focus:ring-primary/40 shadow-sm transition-all border border-white/60"
            placeholder="Search location (e.g. Bengaluru, Mumbai, Delhi, Tokyo)..."
            type="text"
            value={searchVal}
            onChange={(e) => setSearchVal(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <kbd className="absolute right-3 px-1.5 py-0.5 rounded bg-surface-container-high font-code-sm text-[10px] text-on-surface-variant">
            ⌘K
          </kbd>
          {(matches.length > 0 || searchError) && (
            <div className="absolute top-11 inset-x-0 z-50 rounded-xl border border-surface-variant/50 bg-surface-container-lowest shadow-xl overflow-hidden">
              {matches.map((match) => <button key={`${match.latitude},${match.longitude}`} type="button" onClick={() => chooseLocation(match)} className="block w-full text-left px-4 py-3 hover:bg-surface-container-high/60 text-on-surface">
                <span className="block font-semibold text-sm">{match.name}</span><span className="block text-xs text-on-surface-variant">{match.latitude.toFixed(3)}°, {match.longitude.toFixed(3)}°</span>
              </button>)}
              {searchError && <p className="px-4 py-3 text-sm text-error">{searchError}</p>}
            </div>
          )}
          {searching && <span className="absolute right-12 text-xs text-on-surface-variant">Searching…</span>}
        </div>
      </div>

      {/* Right Telemetry and Status */}
      <div className="flex items-center gap-space-md">
        <div className="hidden xl:flex items-center gap-space-xs font-label-md text-label-md text-on-surface-variant px-space-sm py-1 rounded-full bg-surface-container-low/60">
          <span className="material-symbols-outlined text-outline text-[16px]">schedule</span>
          <span>{currentTime || "UTC Operational Stream"}</span>
        </div>

        <div className="hidden md:flex items-center gap-space-xs px-space-md py-1 rounded-full bg-secondary-fixed/50 text-on-secondary-fixed-variant">
          <span className="w-2 h-2 rounded-full bg-secondary animate-pulse" />
          <span className="font-label-md text-label-md font-semibold">Engine: v4.2 NeuralBlend Active</span>
        </div>

        {/* Notifications */}
        <div className="relative flex items-center justify-center">
          <button
            className="w-9 h-9 rounded-full bg-surface-container-lowest/80 hover:bg-surface-container-high/80 text-on-surface-variant hover:text-on-surface flex items-center justify-center shadow-sm transition-all relative border border-white/60"
            type="button"
            title="Notifications"
          >
            <span className="material-symbols-outlined text-[20px]">notifications</span>
            <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-error rounded-full ring-2 ring-surface-container-lowest" />
          </button>
        </div>

        <div className="h-6 w-px bg-surface-variant/60" />

        {/* User Profile */}
        <div className="flex items-center gap-space-sm">
          <div className="relative">
            <div className="w-8 h-8 rounded-full overflow-hidden ring-2 ring-surface-container-lowest shadow-sm bg-gradient-to-tr from-primary to-secondary flex items-center justify-center text-white text-xs font-bold">
              DR
            </div>
            <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-primary rounded-full flex items-center justify-center ring-1 ring-surface-container-lowest">
              <span className="material-symbols-outlined text-on-primary text-[8px] font-bold">check</span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
