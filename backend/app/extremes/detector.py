from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.schemas.weather import BlendedForecastPoint, ExtremeEvent

logger = get_logger(__name__)


def model_agreement(samples: Sequence[float], peak_value: float) -> float:
    """Agreement of the member models on a peak value, in [0, 1].

    Computed as 1 - (coefficient of variation of the members) scaled by how
    far their values are from the peak. Returns 1.0 only when the members are
    both tightly clustered and near the reported peak.

    The previous implementation returned a constant per event type
    (0.88/0.84/0.79/0.86/0.91) that had no relationship to the forecast that
    triggered the event.
    """
    vals = [float(v) for v in samples if v is not None]
    if len(vals) < 2:
        return 0.5
    mean = float(np.mean(vals))
    std = float(np.std(vals))
    scale = max(abs(peak_value), 1e-6)
    cv = std / scale
    agreement = float(np.clip(1.0 - cv, 0.0, 1.0))
    # Also penalise members that sit far below the reported peak, which would
    # otherwise inflate agreement through a small standard deviation.
    if peak_value > 0:
        below = sum(1 for v in vals if v < 0.5 * peak_value) / len(vals)
        agreement *= 1.0 - 0.5 * below
    return round(float(np.clip(agreement, 0.0, 1.0)), 3)


class ExtremeWeatherDetector:
    """Threshold-based hazard detection over the blended trajectory.

    Each event records the window in which it occurs and the measured member
    agreement, rather than asserting a fixed duration and a fixed agreement.
    """

    def detect(
        self,
        *,
        location_name: str,
        forecast_points: List[BlendedForecastPoint],
        member_samples: Optional[Dict[int, List[float]]] = None,
    ) -> List[ExtremeEvent]:
        events: List[ExtremeEvent] = []
        if not forecast_points:
            return events

        member_samples = member_samples or {}
        window = forecast_points[:24]

        # ---- Rainfall: 24 h accumulation and 1 h burst -------------------
        if window:
            rain_24h = sum(pt.precipitation for pt in window)
            peak = max(window, key=lambda p: p.precipitation)
            peak_lead = peak.leadTimeHours

            burst_samples = member_samples.get(peak_lead, [])
            agreement = model_agreement(burst_samples, peak.precipitation)

            if rain_24h >= settings.EXTREME_RAIN_VERY_HEAVY_MM_24H:
                events.append(
                    ExtremeEvent(
                        id="EVT-RAIN-SEVERE",
                        eventType="HEAVY_RAINFALL",
                        severity="HIGH",
                        time=peak.timestamp,
                        leadTimeHours=peak_lead,
                        durationHours=24,
                        intensityValue=round(rain_24h, 1),
                        unit="mm/24h",
                        location=location_name,
                        modelAgreement=agreement,
                        modelAgreementBasis="member spread at the peak hour",
                        details=(
                            f"Blended accumulation {rain_24h:.1f} mm over 24 h "
                            f"exceeds the {settings.EXTREME_RAIN_VERY_HEAVY_MM_24H:.1f} mm "
                            f"very-heavy threshold. Peak hour {peak.timestamp} at "
                            f"{peak.precipitation:.1f} mm/h."
                        ),
                    )
                )
            elif rain_24h >= settings.EXTREME_RAIN_HEAVY_MM_24H:
                events.append(
                    ExtremeEvent(
                        id="EVT-RAIN-HEAVY",
                        eventType="HEAVY_RAINFALL",
                        severity="MODERATE",
                        time=window[0].timestamp,
                        leadTimeHours=window[0].leadTimeHours,
                        durationHours=24,
                        intensityValue=round(rain_24h, 1),
                        unit="mm/24h",
                        location=location_name,
                        modelAgreement=agreement,
                        modelAgreementBasis="member spread at the peak hour",
                        details=(
                            f"Blended accumulation {rain_24h:.1f} mm over 24 h "
                            f"exceeds the {settings.EXTREME_RAIN_HEAVY_MM_24H:.1f} mm "
                            f"heavy threshold; peak {peak.precipitation:.1f} mm/h at "
                            f"{peak.timestamp}."
                        ),
                    )
                )

            # The burst check is independent of the accumulation check, so a
            # severe daily total no longer suppresses the hourly burst detail.
            if peak.precipitation >= settings.EXTREME_RAIN_BURST_MM_1H:
                events.append(
                    ExtremeEvent(
                        id="EVT-RAIN-BURST",
                        eventType="CONVECTIVE_BURST",
                        severity="HIGH" if peak.precipitation >= 2 * settings.EXTREME_RAIN_BURST_MM_1H else "MODERATE",
                        time=peak.timestamp,
                        leadTimeHours=peak_lead,
                        durationHours=1,
                        intensityValue=round(peak.precipitation, 1),
                        unit="mm/h",
                        location=location_name,
                        modelAgreement=agreement,
                        modelAgreementBasis="member spread at the peak hour",
                        details=(
                            f"Peak hourly intensity {peak.precipitation:.1f} mm/h at "
                            f"{peak.timestamp} reaches the "
                            f"{settings.EXTREME_RAIN_BURST_MM_1H:.1f} mm/h burst threshold."
                        ),
                    )
                )

        # ---- Wind ---------------------------------------------------------
        if forecast_points:
            gust = max(forecast_points, key=lambda p: p.windSpeed)
            if gust.windSpeed >= settings.EXTREME_WIND_SPEED_KMH:
                wind_samples = [
                    p.windSpeed
                    for p in forecast_points
                    if p.leadTimeHours == gust.leadTimeHours
                ]
                events.append(
                    ExtremeEvent(
                        id="EVT-WIND-HIGH",
                        eventType="HIGH_WIND",
                        severity="HIGH" if gust.windSpeed >= 65.0 else "MODERATE",
                        time=gust.timestamp,
                        leadTimeHours=gust.leadTimeHours,
                        durationHours=_hours_at_or_above(
                            forecast_points, "windSpeed", settings.EXTREME_WIND_SPEED_KMH
                        ),
                        intensityValue=round(gust.windSpeed, 1),
                        unit="km/h",
                        location=location_name,
                        modelAgreement=model_agreement(
                            member_samples.get(gust.leadTimeHours, []), gust.windSpeed
                        )
                        if member_samples.get(gust.leadTimeHours)
                        else 0.5,
                        modelAgreementBasis="member spread at the peak hour",
                        details=(
                            f"Peak blended wind {gust.windSpeed:.1f} km/h from "
                            f"{gust.windDirection:.0f} deg at T+{gust.leadTimeHours} h."
                        ),
                    )
                )

        # ---- Heat ---------------------------------------------------------
        if forecast_points:
            hot = max(forecast_points, key=lambda p: p.temperature)
            if hot.temperature >= settings.EXTREME_HEAT_TEMP_C:
                events.append(
                    ExtremeEvent(
                        id="EVT-HEAT-WAVE",
                        eventType="HEAT_WAVE",
                        severity="HIGH",
                        time=hot.timestamp,
                        leadTimeHours=hot.leadTimeHours,
                        durationHours=_hours_at_or_above(
                            forecast_points, "temperature", settings.EXTREME_HEAT_TEMP_C
                        ),
                        intensityValue=round(hot.temperature, 1),
                        unit="degC",
                        location=location_name,
                        modelAgreement=0.5,
                        modelAgreementBasis="not computed; only precipitation members are archived",
                        details=(
                            f"Peak blended temperature {hot.temperature:.1f} degC at "
                            f"T+{hot.leadTimeHours} h reaches the "
                            f"{settings.EXTREME_HEAT_TEMP_C:.1f} degC threshold."
                        ),
                    )
                )

        return events


def _hours_at_or_above(
    points: Sequence[BlendedForecastPoint], attribute: str, threshold: float
) -> int:
    """Count consecutive hours at or above a threshold, capped at the window."""
    hours = 0
    for pt in points:
        if getattr(pt, attribute) >= threshold:
            hours += 1
        else:
            break
    return max(1, min(hours, len(points)))


extreme_detector = ExtremeWeatherDetector()
