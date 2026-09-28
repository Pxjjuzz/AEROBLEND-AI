from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Dict, List, Mapping, Optional

import numpy as np

from backend.app.features.spec import FEATURE_NAMES, REGIME_FLAGS, build_vector


def _dew_point_approx(temp_c: float, rh_pct: float) -> float:
    """Magnus-Tetens dew point.

    Replaces the previous ``temp - (100 - rh) / 5.0`` linear shortcut, which
    was used both in the feature vector and in the blended output.
    """
    rh = min(max(rh_pct, 1.0), 100.0)
    a, b = 17.625, 243.04
    alpha = (a * temp_c) / (b + temp_c) + math.log(rh / 100.0)
    return (b * alpha) / (a - alpha)


def dew_point_from(temp_c: float, rh_pct: float) -> float:
    return _dew_point_approx(temp_c, rh_pct)


class FeatureEngineer:
    feature_names: List[str] = list(FEATURE_NAMES)

    @staticmethod
    def _parse_time(timestamp_str: str) -> datetime:
        try:
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            # Never fabricate a calendar month here. An unparseable timestamp
            # previously defaulted to month=9/hour=14, which silently biased the
            # diurnal and seasonal features.
            return datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def extract_features(
        self,
        *,
        latitude: float,
        longitude: float,
        elevation: float,
        timestamp_str: str,
        lead_time_hours: int,
        model_forecasts: Mapping[str, Mapping[str, Optional[float]]],
        active_regime: str = "NORMAL",
    ) -> np.ndarray:
        """Build the 19-dim feature vector from the per-model values at one step.

        ``model_forecasts`` maps model_key -> {variable: value}. Models whose
        values are all None are ignored, exactly as the training pipeline does,
        so the runtime and training feature distributions stay aligned.
        """
        dt = self._parse_time(timestamp_str)

        def collect(var: str) -> List[float]:
            out: List[float] = []
            for values in model_forecasts.values():
                v = values.get(var)
                if v is not None:
                    out.append(float(v))
            return out

        temps = collect("temperature")
        hums = collect("humidity")
        press = collect("pressure")
        winds = collect("windSpeed")
        precips = collect("precipitation")
        dews = collect("dewPoint")

        temp_mean = float(np.mean(temps)) if temps else 20.0
        temp_std = float(np.std(temps)) if len(temps) > 1 else 0.0
        hum_mean = float(np.mean(hums)) if hums else 70.0
        pres_mean = float(np.mean(press)) if press else 1013.25
        wind_mean = float(np.mean(winds)) if winds else 10.0
        precip_mean = float(np.mean(precips)) if precips else 0.0
        precip_std = float(np.std(precips)) if len(precips) > 1 else 0.0

        if dews:
            dew_mean = float(np.mean(dews))
        else:
            dew_mean = _dew_point_approx(temp_mean, hum_mean)
        dew_depression = max(0.0, temp_mean - dew_mean)

        raw: Dict[str, float] = {
            "lat": latitude,
            "lon": longitude,
            "elevation": elevation,
            "hour_sin": math.sin(2 * math.pi * dt.hour / 24.0),
            "hour_cos": math.cos(2 * math.pi * dt.hour / 24.0),
            "month_sin": math.sin(2 * math.pi * dt.month / 12.0),
            "month_cos": math.cos(2 * math.pi * dt.month / 12.0),
            "lead_time_hours": lead_time_hours,
            "temp_mean": temp_mean,
            "humidity_mean": hum_mean,
            "pressure_mean": pres_mean,
            "wind_speed_mean": wind_mean,
            "precip_mean": precip_mean,
            "precip_std": precip_std,
            "temp_std": temp_std,
            "dew_point_depression": dew_depression,
            "regime_convective": 1.0 if active_regime == "CONVECTIVE" else 0.0,
            "regime_monsoon": 1.0 if active_regime == "MONSOON" else 0.0,
            "regime_extreme": 1.0 if active_regime == "EXTREME" else 0.0,
        }
        return build_vector(raw)


feature_engineer = FeatureEngineer()
