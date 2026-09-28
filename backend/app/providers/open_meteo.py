from __future__ import annotations

import asyncio
import math
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from backend.app.core.config import KEY_TO_SPEC, MODEL_KEYS, settings
from backend.app.core.logging import get_logger
from backend.app.providers.base import ProviderError, TTLCache, WeatherProvider
from backend.app.schemas.weather import ForecastPoint, ProviderHealth

logger = get_logger(__name__)

HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "precipitation",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "cloud_cover",
    "weather_code",
]


class OpenMeteoProvider(WeatherProvider):
    def __init__(self) -> None:
        super().__init__("Open-Meteo")
        self.base_url = settings.OPEN_METEO_BASE_URL
        self.archive_url = settings.OPEN_METEO_ARCHIVE_URL
        self._forecast_cache = TTLCache(settings.CACHE_MAX_ENTRIES)
        self._archive_cache = TTLCache(8)
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()
        # The pool holds sockets bound to the loop that opened it. If the
        # process later runs on a different loop (a new TestClient portal, an
        # in-process restart, a worker fork), reusing the client yields
        # "Event loop is closed" from the transport. Track the owning loop and
        # rebuild the pool when it changes.
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None

    # -- HTTP plumbing -------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        """One pooled client per event loop.

        A fresh AsyncClient per request (the old behaviour) discarded the
        connection pool and paid a full TCP+TLS handshake every call.
        """
        running = asyncio.get_running_loop()
        if self._client is not None and self._client_loop is not running:
            stale, self._client, self._client_loop = self._client, None, None
            try:
                await stale.aclose()
            except Exception:  # pragma: no cover - best-effort teardown
                logger.debug("stale provider client close failed", exc_info=True)

        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    limits = httpx.Limits(
                        max_connections=settings.HTTP_MAX_CONNECTIONS,
                        max_keepalive_connections=settings.HTTP_MAX_CONNECTIONS,
                    )
                    self._client = httpx.AsyncClient(
                        timeout=httpx.Timeout(settings.HTTP_TIMEOUT_SECONDS),
                        limits=limits,
                        headers={"User-Agent": "AeroBlend-AI/5.0"},
                        follow_redirects=True,
                    )
                    self._client_loop = running
        return self._client

    async def _request_json(
        self, url: str, params: Dict[str, Any], *, timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        client = await self._get_client()
        last_error: Optional[Exception] = None
        for attempt in range(1, settings.HTTP_MAX_RETRIES + 1):
            try:
                request_params = {k: v for k, v in params.items() if v is not None}
                if settings.OPEN_METEO_API_KEY:
                    request_params["apikey"] = settings.OPEN_METEO_API_KEY
                response = await client.get(
                    url,
                    params=request_params,
                    timeout=timeout or settings.HTTP_TIMEOUT_SECONDS,
                )
                if response.status_code == 429:
                    # Do not hammer a rate limit we cannot escape without an
                    # API key; fail fast with an explicit status.
                    raise ProviderError(
                        "Open-Meteo rate limit exceeded. Configure "
                        "OPEN_METEO_API_KEY to raise the quota.",
                        upstream_status=429,
                    )
                response.raise_for_status()
                return response.json()
            except ProviderError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < settings.HTTP_MAX_RETRIES:
                    # Exponential backoff with jitter. asyncio has no .random
                    # attribute; the previous code raised AttributeError here,
                    # which turned every retryable failure into a hard error
                    # instead of a backoff.
                    delay = min(2.0 ** (attempt - 1), 8.0) * (0.5 + random.random() * 0.5)
                    await asyncio.sleep(delay)
        raise ProviderError(
            f"{self.name} request failed after {settings.HTTP_MAX_RETRIES} attempts: {last_error}"
        )

    async def search_locations(self, query: str, count: int = 8) -> List[Dict[str, Any]]:
        """Resolve a user-entered place through Open-Meteo's live geocoder."""
        payload = await self._request_json(
            "https://geocoding-api.open-meteo.com/v1/search",
            {"name": query, "count": count, "language": "en", "format": "json"},
            timeout=10.0,
        )
        results: List[Dict[str, Any]] = []
        for item in payload.get("results") or []:
            lat, lon = item.get("latitude"), item.get("longitude")
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
                continue
            parts = [item.get("name"), item.get("admin1"), item.get("country")]
            results.append(
                {
                    "name": ", ".join(str(part) for part in parts if part),
                    "latitude": lat,
                    "longitude": lon,
                    "elevation": item.get("elevation"),
                    "country": item.get("country"),
                    "admin1": item.get("admin1"),
                    "timezone": item.get("timezone"),
                }
            )
        return results

    # -- Wind helpers --------------------------------------------------------

    @staticmethod
    def _calculate_uv_wind(
        speed_kmh: Optional[float], direction_deg: Optional[float]
    ) -> Tuple[Optional[float], Optional[float]]:
        """Meteorological convention: direction is the direction wind blows FROM.

        u = -speed*sin(dir) (eastward component)
        v = -speed*cos(dir) (northward component)
        """
        if speed_kmh is None or direction_deg is None:
            return None, None
        speed_ms = speed_kmh / 3.6
        rad = math.radians(direction_deg)
        return round(-speed_ms * math.sin(rad), 3), round(-speed_ms * math.cos(rad), 3)

    @staticmethod
    def _uv_to_speed_dir(
        u: Optional[float], v: Optional[float]
    ) -> Tuple[Optional[float], Optional[float]]:
        """Inverse of _calculate_uv_wind, in km/h and meteorological degrees."""
        if u is None or v is None:
            return None, None
        speed_ms = math.hypot(u, v)
        direction = (math.degrees(math.atan2(-u, -v)) + 360.0) % 360.0
        return round(speed_ms * 3.6, 2), round(direction, 1)

    # -- Forecast ------------------------------------------------------------

    async def fetch_forecast(
        self, latitude: float, longitude: float, forecast_days: int
    ) -> Dict[str, List[ForecastPoint]]:
        points, _ = await self.fetch_forecast_with_elevation(
            latitude, longitude, forecast_days
        )
        return points

    async def fetch_forecast_with_elevation(
        self, latitude: float, longitude: float, forecast_days: int
    ) -> Tuple[Dict[str, List[ForecastPoint]], float]:
        """Forecast plus the grid-cell elevation the provider resolved.

        Elevation is a gating-network feature and drives the orographic index,
        so it must come from real terrain data rather than a name lookup.
        """
        cache_key = f"fc:{round(latitude, 3)}:{round(longitude, 3)}:{forecast_days}"
        cached = await self._forecast_cache.get(cache_key)
        if cached is not None:
            return cached

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(HOURLY_VARIABLES),
            "models": ",".join(spec.slug for spec in KEY_TO_SPEC.values()),
            "forecast_days": forecast_days,
            "wind_speed_unit": "kmh",
            # Pin the axis to UTC. Previously the default local-time axis was
            # used, which silently shifted the diurnal features.
            "timezone": "UTC",
        }
        payload = await self._request_json(f"{self.base_url}/forecast", params)

        result = self._parse_forecast_payload(
            payload, latitude=latitude, longitude=longitude
        )
        await self._forecast_cache.set(cache_key, result, settings.WEATHER_CACHE_TTL)
        return result

    def _parse_forecast_payload(
        self, payload: Dict[str, Any], *, latitude: float, longitude: float
    ) -> Tuple[Dict[str, List[ForecastPoint]], float]:
        """Build the per-model point lists and detect which models are empty.

        Returns the points plus the grid elevation reported by the API, which is
        used for terrain-aware feature extraction.
        """
        elevation = payload.get("elevation")
        elevation = float(elevation) if isinstance(elevation, (int, float)) else 0.0

        hourly = payload.get("hourly") or {}
        times: List[str] = hourly.get("time") or []
        now = datetime.now(timezone.utc)

        result: Dict[str, List[ForecastPoint]] = {key: [] for key in MODEL_KEYS}

        for model_key in MODEL_KEYS:
            spec = KEY_TO_SPEC[model_key]
            series = {var: hourly.get(f"{var}_{spec.slug}") for var in HOURLY_VARIABLES}

            for idx, t_str in enumerate(times):
                values = {}
                for var, arr in series.items():
                    values[var] = arr[idx] if arr is not None and idx < len(arr) else None
                    if values[var] == "":
                        values[var] = None

                if all(v is None for v in values.values()):
                    continue

                parsed = self._parse_utc(t_str)
                lead_hours = int(round((parsed - now).total_seconds() / 3600.0))

                u, v = self._calculate_uv_wind(
                    values["wind_speed_10m"], values["wind_direction_10m"]
                )
                result[model_key].append(
                    ForecastPoint(
                        timestamp=t_str,
                        validTime=parsed.isoformat().replace("+00:00", "Z"),
                        latitude=latitude,
                        longitude=longitude,
                        temperature=_f(values["temperature_2m"]),
                        humidity=_f(values["relative_humidity_2m"]),
                        dewPoint=_f(values["dew_point_2m"]),
                        pressure=_f(values["surface_pressure"]),
                        windSpeed=_f(values["wind_speed_10m"]),
                        windDirection=_f(values["wind_direction_10m"]),
                        windU=u,
                        windV=v,
                        precipitation=_f(values["precipitation"]),
                        cloudCover=_f(values["cloud_cover"]),
                        weatherCode=int(values["weather_code"])
                        if values["weather_code"] is not None
                        else None,
                        modelName=model_key,
                        provider=self.name,
                        modelRun=self._infer_run_cycle(model_key, now),
                        leadTimeHours=lead_hours,
                    )
                )
        return result, elevation

    @staticmethod
    def _parse_utc(value: str) -> datetime:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    @staticmethod
    def _infer_run_cycle(model_key: str, now: datetime) -> str:
        """Derive the model's most recent operational cycle from the wall clock.

        Previously a single wall-clock-derived cycle string was invented for
        every model, which is wrong for models on different cycles.
        """
        cycle_hours = 12 if model_key in ("ECMWF_IFS", "ECMWF_AIFS") else 6
        latest = now.replace(minute=0, second=0, microsecond=0)
        latest = latest.replace(hour=(latest.hour // cycle_hours) * cycle_hours)
        return f"{latest:%Y-%m-%dT}{latest.hour:02d}Z"

    @staticmethod
    def available_models(
        model_forecasts: Dict[str, List[ForecastPoint]]
    ) -> List[str]:
        """Models that actually carry data.

        Open-Meteo currently returns an all-null payload for ecmwf_aifs025.
        The old code trusted the requested slug, so the provider health page
        reported AIFS as OPERATIONAL while it contributed nothing.
        """
        return [k for k, v in model_forecasts.items() if any(p.temperature is not None for p in v)]

    # -- Health --------------------------------------------------------------

    async def check_health(self) -> List[ProviderHealth]:
        """Probe each model with its own request so a dead model is visible."""
        lat, lon = settings.DEFAULT_LATITUDE, settings.DEFAULT_LONGITUDE
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        async def probe(model_key: str) -> Tuple[ProviderHealth, Optional[str]]:
            spec = KEY_TO_SPEC[model_key]
            started = time.perf_counter()
            status = "OPERATIONAL"
            error: Optional[str] = None
            try:
                payload = await self._request_json(
                    f"{self.base_url}/forecast",
                    {
                        "latitude": lat,
                        "longitude": lon,
                        "hourly": "temperature_2m",
                        "models": spec.slug,
                        "forecast_days": 1,
                        "timezone": "UTC",
                    },
                    timeout=10.0,
                )
                series = (payload.get("hourly") or {}).get("temperature_2m")
                # A slug can be accepted by the API and still return no data.
                populated = sum(1 for v in (series or []) if v is not None and v != "")
                if not populated:
                    status = "UNAVAILABLE"
                    error = "provider returned an empty series for this model"
            except ProviderError as exc:
                status = "UNAVAILABLE"
                error = str(exc)
            except Exception as exc:  # pragma: no cover - defensive
                status = "UNAVAILABLE"
                error = str(exc)

            latency = round((time.perf_counter() - started) * 1000.0, 1)
            return (
                ProviderHealth(
                    provider=self.name,
                    model=model_key,
                    displayName=spec.display_name,
                    status=status,
                    latencyMs=latency,
                    lastSuccessfulRun=now_str if status == "OPERATIONAL" else None,
                    lastChecked=now_str,
                    updateFrequency=spec.update_cycle,
                    coverage="Global",
                    resolution=spec.native_resolution,
                    error=error,
                ),
                error,
            )

        results = await asyncio.gather(*(probe(k) for k in MODEL_KEYS))
        for health, error in results:
            if error:
                logger.warning(
                    "provider health degraded",
                    extra={"context": {"model": health.model, "error": error}},
                )
        return [h for h, _ in results]

    # -- Archive (verification + analogues) ----------------------------------

    async def fetch_historical_archive(
        self,
        latitude: float,
        longitude: float,
        start_date: str,
        end_date: str,
        *,
        variables: Optional[List[str]] = None,
        include_models: bool = False,
    ) -> Dict[str, Any]:
        """ERA5 reanalysis, optionally with per-model archived series.

        Used by the verification engine (reference + per-model forecasts) and
        by the analogue search. This was previously implemented but never
        called by anything in the codebase.
        """
        variables = variables or [
            "temperature_2m",
            "relative_humidity_2m",
            "surface_pressure",
            "wind_speed_10m",
            "precipitation",
        ]
        cache_key = (
            f"ar:{round(latitude, 2)}:{round(longitude, 2)}:{start_date}:{end_date}:"
            f"{'m' if include_models else 'r'}"
        )
        cached = await self._archive_cache.get(cache_key)
        if cached is not None:
            return cached

        params: Dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date,
            "end_date": end_date,
            "hourly": ",".join(variables),
            "timezone": "UTC",
        }
        if include_models:
            params["models"] = ",".join(spec.slug for spec in KEY_TO_SPEC.values())

        payload = await self._request_json(
            f"{self.archive_url}/archive", params, timeout=90.0
        )
        await self._archive_cache.set(
            cache_key, payload, settings.ARCHIVE_CACHE_TTL
        )
        return payload

    # -- Housekeeping --------------------------------------------------------

    async def clear_caches(self) -> None:
        await self._forecast_cache.clear()
        await self._archive_cache.clear()

    def close(self) -> None:
        if self._client is not None:
            # Fire-and-forget is safe here: the app is shutting down.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                loop.create_task(self._client.aclose())
            self._client = None


def _f(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    # Open-Meteo encodes missing values as NaN in some series.
    if math.isnan(out) or math.isinf(out):
        return None
    return out


open_meteo_provider = OpenMeteoProvider()
