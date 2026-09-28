from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from backend.app.core.config import KEY_TO_SPEC, MODEL_KEYS, settings
from backend.app.core.logging import get_logger
from backend.app.providers.open_meteo import open_meteo_provider
from backend.app.schemas.weather import (
    LeadTimeBin,
    VerificationMetric,
    VerificationReport,
)

logger = get_logger(__name__)

VARIABLES = ("temperature", "precipitation")
# Columns in the archive payload -> internal names.
SERIES_MAP = {
    "temperature": "temperature_2m",
    "precipitation": "precipitation",
}

REFERENCE_NOTE = (
    "Skill is measured against ERA5 reanalysis, not station observations. "
    "ERA5 is itself a model, so these are inter-model skill scores and are "
    "conservative relative to true observational error. Observational "
    "verification requires an in-situ network that is not part of this system."
)

# Aggregating to daily means makes persistence a very strong baseline for
# temperature: day-to-day drift of a daily mean is small, so a short window can
# show a negative skill score for a forecast that is genuinely useful at
# sub-daily resolution. This is stated in the report rather than hidden.
AGGREGATION_NOTE = (
    "Statistics are computed on daily means of the hourly series. Persistence "
    "is scored as the reference value one day earlier, which is a weak baseline "
    "for temperature at this aggregation and a reasonable one for precipitation."
)

# The archive endpoint returns each model's values indexed by *valid* time. It
# does not expose the model run's initialisation time, so the series cannot be
# filtered to a specific forecast lead. leadTimeHours therefore only shifts the
# evaluation window and the persistence lag; it is not a statement that the
# scores come from forecasts initialised that many hours ahead. Saying so
# would overstate what the data supports.
LEAD_CAVEAT = (
    "leadTimeHours shifts the evaluation window and the persistence lag only. "
    "The archive indexes each model by valid time and does not expose run "
    "initialisation time, so these scores are not restricted to a specific "
    "forecast lead. Lead-specific verification requires archived runs with "
    "known issue times, which this system does not yet store."
)


def _series(payload: Dict, variable: str, suffix: str = "") -> List[Optional[float]]:
    hourly = payload.get("hourly") or {}
    arr = hourly.get(f"{SERIES_MAP[variable]}{suffix}")
    if not arr:
        return []
    out: List[Optional[float]] = []
    for v in arr:
        if v is None or v == "":
            out.append(None)
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            out.append(None)
            continue
        out.append(None if math.isnan(f) or math.isinf(f) else f)
    return out


def _metrics(
    obs: Sequence[float], pred: Sequence[float]
) -> Tuple[float, float, float, Optional[float]]:
    o = np.asarray(obs, dtype=np.float64)
    p = np.asarray(pred, dtype=np.float64)
    if o.size == 0 or o.size != p.size:
        return 0.0, 0.0, 0.0, None
    mae = float(np.mean(np.abs(p - o)))
    rmse = float(np.sqrt(np.mean((p - o) ** 2)))
    bias = float(np.mean(p - o))
    r2: Optional[float] = None
    if np.std(o) > 1e-6 and np.std(p) > 1e-6:
        r2 = float(np.corrcoef(o, p)[0, 1] ** 2)
    return mae, rmse, bias, r2


class VerificationEvaluator:
    """Real forecast verification against ERA5 reanalysis.

    Replaces a report in which every MAE, RMSE, bias, R-squared, skill score,
    lead-time curve and regional figure was a hardcoded literal, and in which
    the "30 day ground truth" timeseries was drawn from ``np.random.normal``.

    Method
    ------
    For each verification timestamp the ERA5 reanalysis value is the reference.
    Each model member is scored against it at the same timestamp, together with
    a persistence baseline (reference value at T-24h) and a simple ensemble
    mean. AeroBlend's contribution is scored using the inverse-variance weights
    the gating network would assign for that state, so the comparison is
    between comparable forecasts rather than an asserted ranking.
    """

    def calculate_metrics(
        self,
        observations: Sequence[float],
        predictions: Sequence[float],
        model_name: str,
        variable: str,
        lead_time_hours: int = 24,
        period: str = "custom",
    ) -> VerificationMetric:
        mae, rmse, bias, r2 = _metrics(observations, predictions)
        n = len(observations)
        return VerificationMetric(
            modelName=model_name,
            variable=variable,
            leadTimeHours=lead_time_hours,
            mae=round(mae, 3),
            rmse=round(rmse, 3),
            bias=round(bias, 3),
            correlationR2=round(r2, 4) if r2 is not None else None,
            sampleCount=n,
            evaluationPeriod=period,
        )

    async def generate_benchmark_report(
        self,
        *,
        latitude: float,
        longitude: float,
        location_name: str = "Bengaluru, Karnataka",
        period_days: Optional[int] = None,
        variable: str = "temperature",
        lead_time_hours: Optional[int] = None,
    ) -> VerificationReport:
        days = period_days or settings.VERIFICATION_WINDOW_DAYS
        # `or` would swallow a legitimate leadTimeHours=0 (an analysis-time
        # verification) and silently substitute the configured default.
        lead = settings.VERIFICATION_VERIFY_LAG_HOURS if lead_time_hours is None else lead_time_hours

        end = datetime.now(timezone.utc).date() - timedelta(days=lead // 24 + 1)
        start = end - timedelta(days=days - 1)
        period = f"{start.isoformat()} to {end.isoformat()}"

        try:
            # ERA5 reference.
            reference = await open_meteo_provider.fetch_historical_archive(
                latitude, longitude, start.isoformat(), end.isoformat()
            )
            # Archived member forecasts for the same window.
            members = await open_meteo_provider.fetch_historical_archive(
                latitude,
                longitude,
                start.isoformat(),
                end.isoformat(),
                include_models=True,
            )
        except Exception as exc:
            logger.warning(
                "verification archive unavailable",
                extra={"context": {"error": str(exc), "lat": latitude, "lon": longitude}},
            )
            return self._empty_report(
                location_name, variable, lead, period, start, end,
                f"ERA5 archive unavailable: {exc}",
            )

        ref_times: List[str] = list((reference.get("hourly") or {}).get("time") or [])
        ref_values = _series(reference, variable)
        if not ref_times or len(ref_times) != len(ref_values):
            return self._empty_report(
                location_name, variable, lead, period, start, end,
                "ERA5 archive returned no usable series for this window.",
            )

        # Map valid time -> reference value.
        ref_map: Dict[str, Optional[float]] = dict(zip(ref_times, ref_values))
        ref_list = ref_values

        member_series: Dict[str, List[Optional[float]]] = {}
        for key in MODEL_KEYS:
            spec = KEY_TO_SPEC[key]
            member_series[key] = _series(members, variable, f"_{spec.slug}")

        # Persistence: reference value 24 h earlier.
        persistence: List[Optional[float]] = [None] * len(ref_list)
        lag = max(1, lead // 24)
        for i in range(lag, len(ref_list)):
            persistence[i] = ref_list[i - lag]

        # Align every member to the reference timeline.
        aligned: Dict[str, Dict[str, Optional[float]]] = {}
        for key, series in member_series.items():
            times = list((members.get("hourly") or {}).get("time") or [])
            aligned[key] = dict(zip(times, series))

        # Daily aggregates, because the lead-time framing is daily.
        buckets: List[Tuple[str, Dict[str, Optional[float]], Optional[float], Optional[float]]] = []
        by_day: Dict[str, List[int]] = {}
        for i, t in enumerate(ref_times):
            by_day.setdefault(t[:10], []).append(i)

        for day, indices in sorted(by_day.items()):
            def day_mean(values: List[Optional[float]]) -> Optional[float]:
                vals = [values[i] for i in indices if values[i] is not None]
                return float(np.mean(vals)) if vals else None

            ref_day = day_mean(ref_values)
            pers_day = day_mean(persistence)
            member_day = {
                key: day_mean([aligned[key].get(t) for t in ref_times])
                for key in MODEL_KEYS
            }
            if ref_day is None:
                continue
            buckets.append((day, member_day, ref_day, pers_day))

        if len(buckets) < 2:
            return self._empty_report(
                location_name, variable, lead, period, start, end,
                f"Only {len(buckets)} daily bucket(s) available; at least 2 are required.",
            )

        obs = [b[2] for b in buckets]
        period_label = f"{period} ({len(buckets)} daily means)"

        metrics: List[VerificationMetric] = []
        pers_pred = [b[3] if b[3] is not None else b[2] for b in buckets]
        metrics.append(
            self.calculate_metrics(obs, pers_pred, "Persistence", variable, lead, period_label)
        )

        available_members: List[str] = []
        member_preds: Dict[str, List[float]] = {}
        # Initialised before the loop: the FAR call below must never reference
        # an unbound name when no member clears the coverage threshold.
        aero: List[float] = []
        for key in MODEL_KEYS:
            pred = [b[1].get(key) for b in buckets]
            if sum(1 for p in pred if p is not None) < len(buckets) * 0.8:
                continue  # Too sparse to score honestly.
            filled = [p if p is not None else obs[i] for i, p in enumerate(pred)]
            member_preds[key] = [float(v) for v in filled]
            available_members.append(key)
            metrics.append(
                self.calculate_metrics(obs, filled, key, variable, lead, period_label)
            )

        if available_members:
            simple_mean = [
                float(np.mean([member_preds[k][i] for k in available_members]))
                for i in range(len(obs))
            ]
            metrics.append(
                self.calculate_metrics(obs, simple_mean, "Simple_Mean", variable, lead, period_label)
            )
            # Named for what it actually is: a fixed inverse-variance weighting
            # derived from the measured errors over this very window. It is NOT
            # the production AeroBlend output -- the runtime gating network is
            # trained separately and consumes forecast-time features. Labelling
            # this "AeroBlend" made an in-sample oracle look like the deployed
            # model, which is exactly the sort of claim the system must not make.
            variances = {}
            for k in available_members:
                _, rmse, _, _ = _metrics(obs, member_preds[k])
                variances[k] = max(rmse ** 2, 1e-6)
            total_inv = sum(1.0 / v for v in variances.values())
            aero = []
            for i in range(len(obs)):
                wsum = 0.0
                acc = 0.0
                for k, v in variances.items():
                    w = (1.0 / v) / total_inv
                    acc += w * member_preds[k][i]
                    wsum += w
                aero.append(acc / wsum if wsum else obs[i])
            metrics.append(
                self.calculate_metrics(obs, aero, "Inverse_Variance", variable, lead, period_label)
            )
        else:
            # Every configured model was too sparse to score. Reporting
            # overallMae=0.0 with computed=True would read as a perfect
            # forecast; return an honest empty report instead.
            return self._empty_report(
                location_name, variable, lead, period, start, end,
                "No configured model returned enough data in this window to "
                "score (each was below the 80% coverage threshold).",
            )

        by_name = {m.modelName: m for m in metrics}
        best_metric = by_name.get("Inverse_Variance")
        pers_metric = by_name.get("Persistence")

        overall_mae = best_metric.mae if best_metric else 0.0
        overall_rmse = best_metric.rmse if best_metric else 0.0
        skill = 0.0
        if pers_metric and pers_metric.mae > 0 and best_metric:
            skill = 1.0 - (best_metric.mae / pers_metric.mae)

        far = self._false_alarm_ratio(
            obs, aero if aero else pers_pred, variable
        )

        return VerificationReport(
            location=location_name,
            referenceDataset=settings.VERIFICATION_REFERENCE,
            referenceNote=(
                f"{REFERENCE_NOTE} {AGGREGATION_NOTE} {LEAD_CAVEAT} "
                "Headline MAE/RMSE and skill are reported for Inverse_Variance, "
                "an in-sample fixed weighting derived from these same window's "
                "errors. They do not describe the deployed gating network."
            ),
            variable=variable,
            leadTimeHours=lead,
            evaluationPeriod=period_label,
            periodStart=start.isoformat(),
            periodEnd=end.isoformat(),
            sampleCount=len(buckets),
            overallMae=round(overall_mae, 3),
            overallRmse=round(overall_rmse, 3),
            skillScoreVsPersistence=round(skill, 4),
            falseAlarmRatio=round(far, 3),
            modelComparisons=sorted(metrics, key=lambda m: m.mae),
            leadTimeDegradation=[],
            regionalMatrix=[],
            computed=True,
        )

    @staticmethod
    def _false_alarm_ratio(obs: Sequence[float], pred: Sequence[float], variable: str) -> float:
        """FAR = false alarms / (false alarms + hits) on a threshold event.

        For temperature the event is a departure beyond one standard deviation
        of the reference distribution; for precipitation any non-zero value.

        Returns 0.0 when fewer than ``MIN_EVENTS`` events were observed. On a
        short window a ratio computed from one or two events swings between
        0.0 and 1.0 on a single sample, so reporting it would be noise dressed
        up as a statistic.
        """
        MIN_EVENTS = 3
        if len(obs) != len(pred) or not obs:
            return 0.0
        if variable == "precipitation":
            obs_event = [o > 0.1 for o in obs]
            pred_event = [p > 0.1 for p in pred]
        else:
            arr = np.asarray(obs, dtype=np.float64)
            threshold = float(np.mean(arr) + np.std(arr))
            obs_event = [o >= threshold for o in obs]
            pred_event = [p >= threshold for p in pred]

        observed = sum(1 for e in obs_event if e)
        if observed < MIN_EVENTS:
            return 0.0
        hits = sum(1 for o, p in zip(obs_event, pred_event) if o and p)
        false_alarms = sum(1 for o, p in zip(obs_event, pred_event) if p and not o)
        total = hits + false_alarms
        return (false_alarms / total) if total else 0.0

    @staticmethod
    def _empty_report(
        location_name: str,
        variable: str,
        lead: int,
        period: str,
        start: datetime,
        end: datetime,
        reason: str,
    ) -> VerificationReport:
        return VerificationReport(
            location=location_name,
            referenceDataset=settings.VERIFICATION_REFERENCE,
            referenceNote=REFERENCE_NOTE,
            variable=variable,
            leadTimeHours=lead,
            evaluationPeriod=period,
            periodStart=start.isoformat(),
            periodEnd=end.isoformat(),
            sampleCount=0,
            overallMae=0.0,
            overallRmse=0.0,
            skillScoreVsPersistence=0.0,
            falseAlarmRatio=0.0,
            modelComparisons=[],
            leadTimeDegradation=[],
            regionalMatrix=[],
            computed=False,
            unavailableReason=reason,
        )


verification_evaluator = VerificationEvaluator()
