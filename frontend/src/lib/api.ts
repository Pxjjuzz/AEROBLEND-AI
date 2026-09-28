const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "/svc/api";

const HEALTH_BASE =
  process.env.NEXT_PUBLIC_HEALTH_URL || "/svc/api";
const locationSearchCache = new Map<string, LocationChoice[]>();

export type LocationChoice = {
  name: string;
  latitude: number;
  longitude: number;
  elevation?: number | null;
  country?: string | null;
  admin1?: string | null;
  timezone?: string | null;
};

export async function searchLocations(query: string): Promise<LocationChoice[]> {
  const normalized = query.trim().toLowerCase();
  const cached = locationSearchCache.get(normalized);
  if (cached) return cached;
  const res = await fetch(`${API_BASE}/weather/locations/search?query=${encodeURIComponent(normalized)}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Location search is unavailable");
  const body = await res.json();
  const results = body.results || [];
  locationSearchCache.set(normalized, results);
  return results;
}

export async function fetchCurrentWeather(lat = 12.9716, lon = 77.5946, locationName = "Bengaluru, Karnataka") {
  const res = await fetch(`${API_BASE}/weather/current?latitude=${lat}&longitude=${lon}&location_name=${encodeURIComponent(locationName)}`, { next: { revalidate: 30 } });
  if (!res.ok) throw new Error("Failed to fetch current weather");
  return res.json();
}

export async function fetchForecast(lat = 12.9716, lon = 77.5946, locationName = "Bengaluru, Karnataka") {
  const res = await fetch(`${API_BASE}/forecast/blended?latitude=${lat}&longitude=${lon}&location_name=${encodeURIComponent(locationName)}`, { next: { revalidate: 30 } });
  if (!res.ok) throw new Error("Failed to fetch forecast");
  return res.json();
}

export async function fetchModels() {
  const res = await fetch(`${API_BASE}/weather/models`, { next: { revalidate: 60 } });
  if (!res.ok) throw new Error("Failed to fetch models");
  return res.json();
}

export async function fetchModelRuns() {
  const res = await fetch(`${API_BASE}/weather/model-runs`, { next: { revalidate: 60 } });
  if (!res.ok) throw new Error("Failed to fetch model runs");
  return res.json();
}

export async function fetchExtremeEvents(lat = 12.9716, lon = 77.5946, locationName = "Bengaluru, Karnataka") {
  const res = await fetch(`${API_BASE}/extreme-events?latitude=${lat}&longitude=${lon}&location_name=${encodeURIComponent(locationName)}`, { next: { revalidate: 30 } });
  if (!res.ok) throw new Error("Failed to fetch extreme events");
  return res.json();
}

export async function fetchExplainability(lat = 12.9716, lon = 77.5946, locationName = "Bengaluru, Karnataka") {
  const res = await fetch(`${API_BASE}/explainability?latitude=${lat}&longitude=${lon}&location_name=${encodeURIComponent(locationName)}`, { next: { revalidate: 30 } });
  if (!res.ok) throw new Error("Failed to fetch explainability");
  return res.json();
}

export async function fetchAnalogues(
  lat = 12.9716,
  lon = 77.5946,
  temp?: number,
  pres?: number,
  hum?: number,
  wind?: number,
  rain?: number
) {
  // The weather parameters are optional. The backend derives any that are
  // omitted from the live blended forecast for these coordinates, so passing
  // hardcoded values here would pin the search state to a stale sea-level
  // default and quietly return the wrong analogues.
  const params = new URLSearchParams({
    latitude: String(lat),
    longitude: String(lon),
  });
  if (temp !== undefined) params.set("temperature", String(temp));
  if (pres !== undefined) params.set("pressure", String(pres));
  if (hum !== undefined) params.set("humidity", String(hum));
  if (wind !== undefined) params.set("wind_speed", String(wind));
  if (rain !== undefined) params.set("precipitation", String(rain));

  const res = await fetch(`${API_BASE}/historical/analogues?${params.toString()}`, { next: { revalidate: 120 } });
  if (!res.ok) throw new Error("Failed to fetch historical analogues");
  return res.json();
}

export async function fetchVerification(
  locationName = "Bengaluru, Karnataka",
  periodDays = 30,
  variable: "temperature" | "precipitation" = "temperature",
  lat = 12.9716,
  lon = 77.5946
) {
  // `period` was never a parameter the backend accepts; it was silently
  // dropped and the server default was used instead, so the UI label implied a
  // window the data did not reflect. period_days is a real day count.
  const params = new URLSearchParams({
    location_name: locationName,
    period_days: String(periodDays),
    variable,
    latitude: String(lat),
    longitude: String(lon),
  });
  const res = await fetch(`${API_BASE}/verification?${params.toString()}`, { next: { revalidate: 60 } });
  if (!res.ok) throw new Error("Failed to fetch verification benchmark");
  return res.json();
}

export async function fetchProviderHealth() {
  const res = await fetch(`${HEALTH_BASE}/health/providers`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch provider health");
  return res.json();
}

export async function fetchMlHealth() {
  const res = await fetch(`${HEALTH_BASE}/health/ml`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch ML health");
  return res.json();
}

export async function fetchDbHealth() {
  const res = await fetch(`${HEALTH_BASE}/health/database`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch database health");
  return res.json();
}
