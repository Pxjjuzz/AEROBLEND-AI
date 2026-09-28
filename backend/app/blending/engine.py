from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from backend.app.blending.gating_network import WeightResult, gating_manager
from backend.app.core.config import MODEL_KEYS
from backend.app.features.engineer import dew_point_from, feature_engineer
from backend.app.schemas.weather import (
    BlendedForecastPoint,
    ForecastPoint,
    ModelWeight,
    WeightDistribution,
    WeatherRegime,
)

# WMO 4677 weather interpretation codes. The previous 18-entry subset silently
# mapped roughly 40 legitimate codes to the catch-all "Cloudy with Rain".
WMO_CODES: Dict[int, str] = {
    0: "Clear Sky", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing Rime Fog",
    51: "Light Drizzle", 53: "Moderate Drizzle", 55: "Dense Drizzle",
    56: "Light Freezing Drizzle", 57: "Dense Freezing Drizzle",
    61: "Slight Rain", 63: "Moderate Rain", 65: "Heavy Rain",
    66: "Light Freezing Rain", 67: "Heavy Freezing Rain",
    71: "Slight Snow Fall", 73: "Moderate Snow Fall", 75: "Heavy Snow Fall",
    77: "Snow Grains",
    80: "Slight Rain Showers", 81: "Moderate Rain Showers", 82: "Violent Rain Showers",
    85: "Slight Snow Showers", 86: "Heavy Snow Showers",
    95: "Thunderstorm", 96: "Thunderstorm with Slight Hail", 99: "Thunderstorm with Heavy Hail",
}

# Hourly accumulation (mm) -> WMO rain code. The previous thresholds mapped
# 5 mm/h to code 65 "Heavy Rain", which is an IMD *daily* category
# (15.6-39.5 mm/24h) incorrectly applied to an hourly value.
HOURLY_RAIN_THRESHOLDS: Sequence[Tuple[float, int]] = ((0.4, 63), (0.1, 61))

SHOWER_CODES = frozenset({80, 81, 82, 95, 96, 99})
DRIZZLE_CODES = frozenset({51, 53, 55, 56, 57})


def weather_text(code: int) -> str:
    return WMO_CODES.get(code, "Unknown Conditions")


def rain_code_for_hourly(mm: float) -> Optional[int]:
    for threshold, code in HOURLY_RAIN_THRESHOLDS:
        if mm >= threshold:
            return code
    return None


@dataclass
class _Step:
    """One aligned timestep, ready for blending."""

    timestamp: str
    valid_time: Optional[str]
    lead_hours: int
    result: WeightResult
    features: Dict[str, Optional[float]]
    codes: Dict[str, Optional[int]]
    points: Dict[str, ForecastPoint]
    # Retained so the explainability engine can perturb the exact vector that
    # produced these weights rather than recomputing it.
    feature_vector: np.ndarray


class BlendingEngine:
    """Adaptive multi-model blending with strict weight conservation.

    For every variable the weighted mean is computed over the models that
    *actually supplied a value*, and the denominator is the sum of *those*
    models' weights.

    The previous implementation added every model's weight to the denominator
    while adding only non-null values to the numerator. Any model returning no
    data therefore divided the total without contributing, depressing the
    result. Because Open-Meteo serves an all-null ``ecmwf_aifs025`` payload, this
    produced a live -6.6 degC temperature error while the API reported status
    "ONLINE - Gating Network: TRAINED".
    """

    @staticmethod
    def _weighted_mean(
        values: Dict[str, Optional[float]], weights: Dict[str, float]
    ) -> Tuple[Optional[float], List[str], float]:
        """Weighted mean over contributing models only.

        Returns ``(value, contributing_keys, weight_coverage)`` where coverage
        is the summed weight that actually contributed.
        """
        acc = 0.0
        total_w = 0.0
        contributors: List[str] = []
        for key, value in values.items():
            if value is None:
                continue
            value = float(value)
            if not math.isfinite(value):
                continue
            w = weights.get(key, 0.0)
            if w <= 0.0:
                continue
            acc += w * value
            total_w += w
            contributors.append(key)
        if total_w <= 0.0:
            return None, [], 0.0
        return acc / total_w, contributors, total_w

    @staticmethod
    def _modal_code(codes: Dict[str, Optional[int]]) -> int:
        """Most common WMO code across the contributing models.

        The old code always read ECMWF_IFS, so the displayed condition had no
        relationship to the blend it was labelling.
        """
        valid = [
            int(c)
            for c in codes.values()
            if c is not None and int(c) in WMO_CODES
        ]
        if not valid:
            return 2
        return max(set(valid), key=valid.count)

    def _resolve_code(
        self, codes: Dict[str, Optional[int]], blended_hourly_mm: float
    ) -> int:
        base = self._modal_code(codes)
        override = rain_code_for_hourly(blended_hourly_mm)
        if override is None:
            return base
        # Do not downgrade an already-convective or drizzle signal.
        if base in SHOWER_CODES or base in DRIZZLE_CODES:
            return base
        return override

    # -- Main entry point ----------------------------------------------------

    def blend(
        self,
        *,
        latitude: float,
        longitude: float,
        elevation: float,
        model_forecasts: Dict[str, List[ForecastPoint]],
        active_regime: WeatherRegime,
        display_lead_time: int = 24,
    ) -> Tuple[List[BlendedForecastPoint], WeightDistribution, List[_Step]]:
        available = {
            key: pts
            for key, pts in model_forecasts.items()
            if pts and any(p.temperature is not None for p in pts)
        }
        empty = WeightDistribution(
            variable="temperature",
            leadTimeHours=display_lead_time,
            weights=[],
            sumWeights=0.0,
            dominantModel="None",
            availableModels=[],
            basis="physical_prior",
        )
        if not available:
            return [], empty, []

        index_map: Dict[str, Dict[str, ForecastPoint]] = {
            key: {p.timestamp: p for p in pts} for key, pts in available.items()
        }

        # Align on timestamps so a model with a shorter horizon does not shift
        # the whole trajectory.
        common: Optional[set[str]] = None
        for mapping in index_map.values():
            keys = set(mapping)
            common = keys if common is None else (common & keys)
        order = sorted(common) if common else sorted(
            min(available.values(), key=len)[i].timestamp
            for i in range(min(len(p) for p in available.values()))
        )

        steps: List[_Step] = []
        for t_str in order:
            points = {k: m[t_str] for k, m in index_map.items() if t_str in m}
            if not points:
                continue
            features = {k: p.temperature for k, p in points.items()}
            codes = {k: p.weatherCode for k, p in points.items()}
            reference = next(iter(points.values()))
            lead_hours = reference.leadTimeHours

            vector = feature_engineer.extract_features(
                latitude=latitude,
                longitude=longitude,
                elevation=elevation,
                timestamp_str=t_str,
                lead_time_hours=lead_hours,
                model_forecasts={
                    k: {
                        "temperature": p.temperature,
                        "humidity": p.humidity,
                        "pressure": p.pressure,
                        "windSpeed": p.windSpeed,
                        "precipitation": p.precipitation,
                        "dewPoint": p.dewPoint,
                    }
                    for k, p in points.items()
                },
                active_regime=active_regime.regime,
            )
            result = gating_manager.predict(
                vector,
                lead_time_hours=float(lead_hours),
                available_models=sorted(points.keys()),
            )
            steps.append(
                _Step(
                    timestamp=t_str,
                    valid_time=reference.validTime,
                    lead_hours=lead_hours,
                    result=result,
                    features=features,
                    codes=codes,
                    points=points,
                    feature_vector=vector,
                )
            )

        if not steps:
            return [], empty, []

        blended: List[BlendedForecastPoint] = []
        for step in steps:
            point = self._build_point(step)
            if point is not None:
                blended.append(point)

        chosen = self._select_step(steps, display_lead_time)
        return blended, self._build_distribution(chosen), steps

    def _select_step(self, steps: List[_Step], display_lead_time: int) -> _Step:
        for step in steps:
            if step.lead_hours == display_lead_time:
                return step
        return min(steps, key=lambda s: abs(s.lead_hours - display_lead_time))

    def _build_point(self, step: _Step) -> Optional[BlendedForecastPoint]:
        weights = step.result.weights
        points = step.points

        def attr(name: str) -> Dict[str, Optional[float]]:
            return {k: getattr(p, name) for k, p in points.items()}

        temp, _, _ = self._weighted_mean(step.features, weights)
        if temp is None:
            return None

        humidity, _, _ = self._weighted_mean(attr("humidity"), weights)
        pressure, _, _ = self._weighted_mean(attr("pressure"), weights)
        dew, _, _ = self._weighted_mean(attr("dewPoint"), weights)
        precip_raw, precip_models, _ = self._weighted_mean(attr("precipitation"), weights)

        # Blend the horizontal components so the vector is preserved, then
        # synthesise speed and meteorological direction.
        u_mean, _, _ = self._weighted_mean(attr("windU"), weights)
        v_mean, _, _ = self._weighted_mean(attr("windV"), weights)
        if u_mean is not None and v_mean is not None:
            wind_speed = round(math.hypot(u_mean, v_mean) * 3.6, 1)
            wind_dir = round((math.degrees(math.atan2(-u_mean, -v_mean)) + 360.0) % 360.0, 1)
        else:
            speed_mean, _, _ = self._weighted_mean(attr("windSpeed"), weights)
            dirs = [v for v in attr("windDirection").values() if v is not None]
            wind_speed = round(speed_mean, 1) if speed_mean is not None else 0.0
            wind_dir = round(float(np.mean(dirs)), 1) if dirs else 0.0

        precip = round(max(0.0, precip_raw), 2) if precip_raw is not None else 0.0
        humidity_val = humidity if humidity is not None else 0.0
        pressure_val = pressure if pressure is not None else 1013.25
        dew_val = dew if dew is not None else dew_point_from(temp, humidity_val)

        samples = [
            max(0.0, float(points[k].precipitation))
            for k in precip_models
            if points[k].precipitation is not None
        ]
        if len(samples) >= 2:
            ci_low = round(max(0.0, float(np.min(samples))), 2)
            ci_high = round(float(np.max(samples)), 2)
            spread = float(np.std(samples))
            basis = "inter-model ensemble envelope (min/max across contributing models)"
        elif len(samples) == 1:
            ci_low = ci_high = round(samples[0], 2)
            spread = 0.0
            basis = "single contributing model; no ensemble envelope available"
        else:
            ci_low = ci_high = precip
            spread = 0.0
            basis = "no precipitation data; envelope not computed"

        confidence = 100.0 - (spread * 4.0 + min(max(step.lead_hours, 0) * 0.25, 25.0))
        if len(step.result.available) < 3:
            # Spread across fewer than three members is not evidence of agreement.
            confidence = min(confidence, 70.0)
        confidence = round(max(45.0, min(98.0, confidence)), 1)

        code = self._resolve_code(step.codes, precip)

        return BlendedForecastPoint(
            timestamp=step.timestamp,
            validTime=step.valid_time,
            leadTimeHours=step.lead_hours,
            temperature=round(temp, 1),
            humidity=round(humidity_val, 1),
            dewPoint=round(dew_val, 1),
            pressure=round(pressure_val, 1),
            windSpeed=wind_speed,
            windDirection=wind_dir,
            precipitation=precip,
            pop=None,
            weatherCode=code,
            conditionText=weather_text(code),
            dominantSource=step.result.dominant,
            confidencePercentage=confidence,
            confidenceIntervalLow=ci_low,
            confidenceIntervalHigh=ci_high,
            uncertaintyBasis=basis,
            contributingModels=list(step.result.available),
        )

    def _build_distribution(self, step: _Step) -> WeightDistribution:
        weights = step.result.weights
        blended, _, _ = self._weighted_mean(step.features, weights)
        entries = [
            ModelWeight(
                modelName=key,
                weight=round(weights.get(key, 0.0), 4),
                forecastValue=step.features.get(key),
                differenceFromBlend=(
                    round(step.features[key] - blended, 2)
                    if step.features.get(key) is not None and blended is not None
                    else None
                ),
                available=key in step.result.available,
            )
            for key in MODEL_KEYS
        ]
        return WeightDistribution(
            variable="temperature",
            leadTimeHours=step.lead_hours,
            weights=entries,
            sumWeights=round(sum(weights.values()), 6),
            dominantModel=step.result.dominant,
            availableModels=list(step.result.available),
            basis=step.result.basis,
        )


blending_engine = BlendingEngine()
