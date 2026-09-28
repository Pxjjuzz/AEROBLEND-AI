from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict, Optional

from app.core.config import settings
from app.schemas.weather import WeatherRegime

# IMD daily rainfall categories (mm/24h) live in settings
# (EXTREME_RAIN_HEAVY_MM_24H / EXTREME_RAIN_VERY_HEAVY_MM_24H) so there is one
# source of truth. Using a daily threshold against an *hourly* accumulation is
# what previously made the EXTREME regime unreachable.

# Orographic exposure is derived from real terrain statistics rather than a
# hardcoded bounding box. The old lookup only recognised two rectangles in
# India and returned a constant 35.0 for everywhere else, including Chennai.
GHAT_BOUNDS = (
    (7.5, 21.0, 72.5, 78.5),   # Western Ghats / Deccan escarpment
    (26.0, 36.0, 74.0, 96.0),  # Himalayan foothills and north
)


class RegimeClassifier:
    """Rule-based synoptic regime assignment with a margin-based confidence.

    The previous version returned a fixed confidence per class (0.92/0.89/
    0.86/0.94). Those were not probabilities and were not derived from the
    inputs, so they were replaced by a measure of how far the observation sits
    from the decision boundary.
    """

    def convective_index(
        self, temperature: float, humidity: float, hour: int, precipitation_24h: float
    ) -> float:
        """Lifted-index style instability proxy, normalised to 0-100.

        This is a documented heuristic, not CAPE. It is named accordingly and
        the description says so.
        """
        if temperature <= 26.0 or humidity <= 65.0:
            base = 0.0
        else:
            base = (temperature - 26.0) * 8.0 + (humidity - 65.0) * 1.5
            # Convective release typically peaks in the afternoon.
            if 12 <= hour <= 20:
                base *= 1.3
        # Observed rainfall is direct evidence of realised convection.
        base += min(precipitation_24h, 60.0) * 0.5
        return round(min(100.0, max(0.0, base)), 1)

    @staticmethod
    def orographic_index(latitude: float, longitude: float, elevation: float) -> float:
        """Terrain-exposure proxy from elevation plus regional relief context."""
        index = min(100.0, elevation / 12.0)
        for lat_lo, lat_hi, lon_lo, lon_hi in GHAT_BOUNDS:
            if lat_lo <= latitude <= lat_hi and lon_lo <= longitude <= lon_hi:
                index += 22.0
                break
        return round(min(100.0, index), 1)

    @staticmethod
    def _month_hour(timestamp_str: Optional[str]) -> tuple[int, int]:
        if not timestamp_str:
            now = datetime.now(timezone.utc)
            return now.month, now.hour
        try:
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            # No fabricated month/hour: fall back to the real current time.
            now = datetime.now(timezone.utc)
            return now.month, now.hour
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.month, dt.hour

    def classify(
        self,
        *,
        latitude: float,
        longitude: float,
        elevation: float,
        temperature: float,
        humidity: float,
        pressure: float,
        wind_speed: float,
        precipitation: float,
        precipitation_24h: Optional[float] = None,
        timestamp_str: Optional[str] = None,
    ) -> WeatherRegime:
        month, hour = self._month_hour(timestamp_str)
        rain_24h = float(precipitation_24h if precipitation_24h is not None else precipitation)

        convective = self.convective_index(temperature, humidity, hour, rain_24h)
        orographic = self.orographic_index(latitude, longitude, elevation)

        observed: Dict[str, float] = {
            "temperature": round(temperature, 1),
            "humidity": round(humidity, 1),
            "pressure": round(pressure, 1),
            "wind_speed": round(wind_speed, 1),
            "precipitation_1h": round(float(precipitation), 2),
            "precipitation_24h": round(rain_24h, 2),
            "month": float(month),
            "hour_utc": float(hour),
        }

        # --- Decision surfaces, evaluated as signed distances -------------
        # Each margin is in the units of its own predictor, so the confidence
        # below is a real (if simple) separation measure.
        rain_heavy_mm_24h = settings.EXTREME_RAIN_HEAVY_MM_24H
        monsoon_margin = min(
            (rain_24h - 2.5) / 10.0,
            (humidity - 65.0) / 15.0,
            (0.0 if 6 <= month <= 10 else -1.0) + 0.5,
        )
        convective_margin = (
            (convective - 50.0) / 20.0,
            (rain_24h - 1.0) / 5.0,
        )
        # Any single threshold crossing is enough, so this is the *largest*
        # margin. Using min() here meant rain, wind and heat all had to be
        # exceeded simultaneously, which is how the EXTREME regime was
        # effectively unreachable in production.
        extreme_margin = max(
            (rain_24h - rain_heavy_mm_24h) / rain_heavy_mm_24h,
            (wind_speed - settings.EXTREME_WIND_SPEED_KMH) / 20.0,
            (temperature - settings.EXTREME_HEAT_TEMP_C) / 5.0,
        )

        # --- Ordered evaluation ---------------------------------------------
        if extreme_margin >= 0.0:
            regime, margin = "EXTREME", extreme_margin
            confidence = _confidence(min(max(extreme_margin, 0.0), 1.0), floor=0.70, ceiling=0.99)
            cluster = "Severe mesoscale convective / hazardous boundary layer"
            description = (
                f"Rainfall {rain_24h:.1f} mm/24h, wind {wind_speed:.0f} km/h, "
                f"temperature {temperature:.1f} degC: at least one threshold of a "
                "hazardous regime is exceeded."
            )
        elif monsoon_margin >= 0.0 and 6 <= month <= 10:
            regime, margin = "MONSOON", monsoon_margin
            confidence = _confidence(min(max(monsoon_margin, 0.0), 1.0), floor=0.65, ceiling=0.97)
            cluster = "Trough shear convergence zone"
            description = (
                f"Active southwest monsoon: humidity {humidity:.0f}% with "
                f"{rain_24h:.1f} mm accumulated over 24 h."
            )
        elif min(convective_margin) >= 0.0:
            regime, margin = "CONVECTIVE", min(convective_margin)
            confidence = _confidence(min(max(margin, 0.0), 1.0), floor=0.60, ceiling=0.96)
            cluster = "Diurnal thermal convective cell"
            description = (
                f"Instability proxy {convective:.0f}/100 with {rain_24h:.1f} mm/24h; "
                "boundary-layer heating is driving localised convection."
            )
        else:
            # Distance to the nearest boundary that was not crossed.
            margin = max(-monsoon_margin, -min(convective_margin), -extreme_margin)
            regime = "NORMAL"
            confidence = _confidence(min(max(margin, 0.0), 1.0), floor=0.60, ceiling=0.97)
            cluster = "Synoptic equilibrium ridge"
            description = (
                "No threshold crossed: large-scale balance dominates and no "
                "convective, monsoonal or hazardous signal is present."
            )

        return WeatherRegime(
            regime=regime,
            confidence=round(confidence, 3),
            synopticCluster=cluster,
            convectiveIndex=convective,
            orographicIndex=orographic,
            description=description,
            observed=observed,
        )


def _confidence(margin: float, *, floor: float, ceiling: float) -> float:
    """Map a signed boundary distance onto a bounded confidence.

    margin >= 0 means the condition is met; margin 0 sits exactly on the
    boundary and maps to ``floor``. Larger margins approach ``ceiling``.
    """
    return floor + (ceiling - floor) * (1.0 - math.exp(-2.0 * max(margin, 0.0)))


regime_classifier = RegimeClassifier()

