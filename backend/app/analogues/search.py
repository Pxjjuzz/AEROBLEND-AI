from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.providers.open_meteo import open_meteo_provider
from backend.app.schemas.weather import AnalogueSearchResult, HistoricalAnalogueMatch

logger = get_logger(__name__)

# The state vector used for matching, with the natural scale of each dimension.
# Rainfall and pressure carry far larger magnitudes than humidity, so an
# unscaled Euclidean distance would let pressure dominate the metric entirely.
STATE_FIELDS: Sequence[Tuple[str, str, float]] = (
    ("temperature_2m", "temperature", 15.0),
    ("surface_pressure", "pressure", 20.0),
    ("relative_humidity_2m", "humidity", 25.0),
    ("wind_speed_10m", "windSpeed", 15.0),
    ("precipitation", "precipitation", 20.0),
)

METHOD = "scaled Euclidean nearest-neighbour over daily mean state vectors"


def _series(payload: Dict, key: str) -> List[Optional[float]]:
    arr = (payload.get("hourly") or {}).get(key)
    if not arr:
        return []
    out: List[Optional[float]] = []
    for v in arr:
        try:
            f = float(v)
        except (TypeError, ValueError):
            out.append(None)
            continue
        out.append(None if math.isnan(f) or math.isinf(f) else f)
    return out


def _mean(values: Sequence[Optional[float]], indices: Sequence[int], minimum: int = 12) -> Optional[float]:
    vals = [values[i] for i in indices if values[i] is not None]
    return float(np.mean(vals)) if len(vals) >= minimum else None


def _max(values: Sequence[Optional[float]], indices: Sequence[int]) -> Optional[float]:
    vals = [values[i] for i in indices if values[i] is not None]
    return float(max(vals)) if vals else None


def _following_24h_total(
    values: Sequence[Optional[float]], day_indices: Sequence[int]
) -> float:
    """Observed precipitation total in the 24 h after a matched day."""
    if not day_indices:
        return 0.0
    last = max(day_indices)
    return float(sum(v for v in values[last + 1 : last + 25] if v is not None))


class HistoricalAnalogueSearch:
    """Topological nearest-neighbour search over ERA5 reanalysis.

    Replaces a function that ignored all seven of its arguments and returned
    three fixed records, while the API layer advertised a "Topological Cosine
    Nearest-Neighbor in Geopotential Space" search across "ECMWF ERA5
    Reanalysis (1980-2025)" that never took place.

    Every similarity score here is computed from the real distance to the query
    against a kernel width derived from the local neighbourhood, and every
    reported outcome is the observed ERA5 state following the match.
    """

    def __init__(self) -> None:
        self._cache: Dict[Tuple[float, float], AnalogueSearchResult] = {}

    async def find_analogues(
        self,
        *,
        latitude: float,
        longitude: float,
        temperature: float,
        pressure: float,
        humidity: float,
        wind_speed: float,
        precipitation: float,
        top_k: int = 5,
        start_year: Optional[int] = None,
    ) -> AnalogueSearchResult:
        query = {
            "temperature": float(temperature),
            "pressure": float(pressure),
            "humidity": float(humidity),
            "windSpeed": float(wind_speed),
            "precipitation": float(precipitation),
        }

        # ANALOGUE_START_YEAR is an absolute calendar year, not a lookback
        # count. Treating it as a lookback produced year 36 AD and a 400.
        start = datetime(max(int(start_year or settings.ANALOGUE_START_YEAR), 1940), 1, 1).date()
        end = datetime.now(timezone.utc).date() - timedelta(days=1)
        if start >= end:
            start = datetime(end.year - 1, 1, 1).date()

        try:
            payload = await open_meteo_provider.fetch_historical_archive(
                latitude, longitude, start.isoformat(), end.isoformat()
            )
        except Exception as exc:
            logger.warning(
                "analogue archive unavailable",
                extra={"context": {"error": str(exc), "lat": latitude, "lon": longitude}},
            )
            return self._empty(latitude, longitude, start, end, f"ERA5 archive unavailable: {exc}")

        times: List[str] = list((payload.get("hourly") or {}).get("time") or [])
        series = {name: _series(payload, key) for key, name, _ in STATE_FIELDS}
        if not times or not all(len(v) == len(times) for v in series.values()):
            return self._empty(
                latitude, longitude, start, end, "ERA5 archive returned no usable series."
            )

        days: Dict[str, List[int]] = {}
        for i, t in enumerate(times):
            days.setdefault(t[:10], []).append(i)

        candidates: List[Tuple[str, Dict[str, float], Dict[str, float]]] = []
        for day, idx in sorted(days.items()):
            state: Dict[str, float] = {}
            for _, name, _ in STATE_FIELDS:
                value = _mean(series[name], idx)
                if value is None:
                    break
                state[name] = value
            if len(state) != len(STATE_FIELDS):
                continue
            outcome = {
                "rainfall_24h": round(_following_24h_total(series["precipitation"], idx), 2),
                "max_temperature": round(
                    _max(series["temperature"], idx) or 0.0, 2
                ),
            }
            candidates.append((day, state, outcome))

        if not candidates:
            return self._empty(
                latitude, longitude, start, end, "No complete daily states in the window."
            )

        names = [n for _, n, _ in STATE_FIELDS]
        scales = np.array([s for _, _, s in STATE_FIELDS], dtype=np.float64)
        q = np.array([query[n] for n in names], dtype=np.float64)

        scored: List[Tuple[float, str, Dict[str, float], Dict[str, float]]] = []
        for day, state, outcome in candidates:
            v = np.array([state[n] for n in names], dtype=np.float64)
            scored.append((float(np.linalg.norm((v - q) / scales)), day, state, outcome))
        scored.sort(key=lambda s: s[0])

        # Kernel width = the distance to the k-th nearest neighbour, so the
        # k-th match scores exp(-0.5) and the first scores close to 1.0. Using
        # the *standard deviation* of the nearest-neighbour distances instead
        # gave a width of ~0.015 against a typical distance of ~5, so every
        # reported similarity collapsed to 0.00%.
        k = min(10, len(scored))
        sigma = max(scored[k - 1][0], 1e-6)

        matches = [
            HistoricalAnalogueMatch(
                date=datetime.fromisoformat(day).strftime("%d %b %Y"),
                location=f"{latitude:.3f}, {longitude:.3f}",
                similarityPercentage=round(
                    min(100.0, math.exp(-(d ** 2) / (2.0 * sigma ** 2)) * 100.0), 2
                ),                synopticMatchName=self._label(state),
                description=(
                    f"ERA5 daily mean {state['temperature']:.1f} degC, "
                    f"{state['humidity']:.0f}% RH, {state['pressure']:.0f} hPa, "
                    f"{state['windSpeed']:.0f} km/h, {state['precipitation']:.1f} mm/day; "
                    f"{outcome['rainfall_24h']:.1f} mm in the following 24 h."
                ),
                matchedState={k: round(v, 2) for k, v in state.items()},
                outcome24h=outcome,
                distance=round(d, 4),
            )
            for d, day, state, outcome in scored[: max(1, top_k)]
        ]

        return AnalogueSearchResult(
            queryCoordinates={"latitude": latitude, "longitude": longitude},
            searchDatabase=settings.VERIFICATION_REFERENCE,
            vectorSimilarityMethod=(
                f"{METHOD} ({len(names)} dimensions); similarity = exp(-d^2 / 2*sigma^2) "
                f"with sigma={sigma:.4f} = distance to the {k}th nearest neighbour"
            ),
            searchWindow={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "daysScanned": len(candidates),
            },
            sampleCount=len(candidates),
            matches=matches,
        )

    @staticmethod
    def _label(state: Dict[str, float]) -> str:
        """Synoptic label derived from the measured state.

        Keys are the internal names declared in STATE_FIELDS.
        """
        humid = state["humidity"] >= 75.0
        wet = state["precipitation"] >= 5.0
        very_wet = state["precipitation"] >= 15.0
        windy = state["windSpeed"] >= 20.0
        low = state["pressure"] < 1005.0
        high = state["pressure"] > 1015.0

        if very_wet:
            return "Deep convective / thunderstorm regime"
        if wet and humid and low:
            return "Monsoon trough and shear convergence"
        if wet and humid:
            return "Orographic rainfall on a relief slope"
        if low:
            return "Cyclonic or low-pressure inflow"
        if windy and not wet:
            return "Post-frontal dry northerly flow"
        if high and not wet:
            return "Stable anticyclonic subsidence"
        return "Mixed synoptic state"

    @staticmethod
    def _empty(
        latitude: float,
        longitude: float,
        start: Optional[datetime],
        end: Optional[datetime],
        reason: str,
    ) -> AnalogueSearchResult:
        logger.info("analogue search returned no matches", extra={"context": {"reason": reason}})
        window: Dict[str, Any] = {"reason": reason}
        if start and end:
            window = {"start": start.isoformat(), "end": end.isoformat()}
        return AnalogueSearchResult(
            queryCoordinates={"latitude": latitude, "longitude": longitude},
            searchDatabase=settings.VERIFICATION_REFERENCE,
            vectorSimilarityMethod=METHOD,
            searchWindow=window,
            sampleCount=0,
            matches=[],
        )


analogue_search = HistoricalAnalogueSearch()
