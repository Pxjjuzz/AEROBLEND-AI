"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { LocationChoice } from "@/lib/api";

const DEFAULT_LOCATION: LocationChoice = {
  name: "Bengaluru, Karnataka, India", latitude: 12.9716, longitude: 77.5946, elevation: 920,
};

type LocationContextValue = { location: LocationChoice; setLocation: (location: LocationChoice) => void };
const LocationContext = createContext<LocationContextValue | null>(null);

export function LocationProvider({ children }: { children: React.ReactNode }) {
  const [location, setLocationState] = useState(DEFAULT_LOCATION);
  useEffect(() => {
    const saved = window.localStorage.getItem("aeroblend-location");
    if (saved) {
      try { setLocationState(JSON.parse(saved)); } catch { window.localStorage.removeItem("aeroblend-location"); }
    }
  }, []);
  const setLocation = (next: LocationChoice) => {
    setLocationState(next);
    window.localStorage.setItem("aeroblend-location", JSON.stringify(next));
  };
  return <LocationContext.Provider value={{ location, setLocation }}>{children}</LocationContext.Provider>;
}

export function useLocation() {
  const value = useContext(LocationContext);
  if (!value) throw new Error("useLocation must be used inside LocationProvider");
  return value;
}
