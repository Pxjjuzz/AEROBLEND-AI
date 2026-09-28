from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.blending.engine import blending_engine
from app.blending.gating_network import gating_manager
from app.core.config import MODEL_KEYS, settings
from app.core.logging import get_logger
from app.database.models import (
    BlendedForecast,
    DisagreementRecord,
    ExtremeEventRecord,
    ForecastRun,
    ForecastValue,
    ModelWeightEntity,
    WeatherRegimeRecord,
)
from app.disagreement.calculator import disagreement_calculator
from app.explainability.explainer import explainability_engine
from app.extremes.detector import extreme_detector
from app.providers.base import ProviderError
from app.providers.open_meteo import open_meteo_provider
from app.regimes.classifier import regime_classifier
from app.schemas.weather import (
    BlendedForecastPoint,
    BlendedForecastResponse,
    ModelDisagreement,
    WeatherRegime,
)
from app.services.location_service import location_resolver

logger = get_logger(__name__)


class ForecastService:
    async def get_blended_forecast(
        self,
        *,
        latitude: float,
        longitude: float,
        location_name: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> BlendedForecastResponse:
        started = time.perf_counter()
        # Cheap mtime check rather than a full reload on every request.
        gating_manager.reload_if_changed()

        status_detail: Optional[str] = None
        try:
            model_forecasts, api_elevation = await self._fetch(latitude, longitude)
        except ProviderError as exc:
            # Honest failure: an explicit DEGRADED/UNAVAILABLE response with a
            # reason. The previous code caught nothing here and, elsewhere,
            # substituted invented weather values while still reporting ONLINE.
            logger.error(
                "forecast provider unavailable",
                extra={"context": {"error": str(exc), "lat": latitude, "lon": longitude}},
            )
            return self._unavailable_response(latitude, longitude, location_name, str(exc))

        available = open_meteo_provider.available_models(model_forecasts)
        unavailable = [k for k in MODEL_KEYS if k not in available]

        if not available:
            status_detail = "All upstream model series were empty."
            return self._unavailable_response(
                latitude, longitude, location_name, status_detail
            )
        if unavailable:
            status_detail = (
                f"Serving {len(available)} of {len(MODEL_KEYS)} models; "
                f"no data for {', '.join(unavailable)}."
            )

        info, matched_id = await location_resolver.resolve(
            db,
            latitude=latitude,
            longitude=longitude,
            location_name=location_name,
            api_elevation=api_elevation,
        )

        # --- Regime from real observations, with a 24 h accumulation --------
        current_pt = self._pick_current(model_forecasts, available)
        if current_pt is None:
            return self._unavailable_response(
                latitude, longitude, location_name, "No model returned a usable current step."
            )

        member_24h = self._accumulate(model_forecasts, available, hours=24)
        regime = self._classify(model_forecasts, available, current_pt, member_24h, info)

        disagreement = disagreement_calculator.calculate(
            values=[member_24h.get(m) for m in available], variable_name="rainfall"
        )

        # --- Blend ---------------------------------------------------------
        elevation = float(info.elevation or 0.0)
        blended_points, weights, steps = blending_engine.blend(
            latitude=latitude,
            longitude=longitude,
            elevation=elevation,
            model_forecasts=model_forecasts,
            active_regime=regime,
            display_lead_time=24,
        )

        if not blended_points:
            return self._unavailable_response(
                latitude, longitude, location_name, "Blending produced no valid timesteps."
            )

        # --- Extremes with measured member spread --------------------------
        member_samples: Dict[int, List[float]] = {}
        for step in steps:
            samples = [
                max(0.0, float(step.points[k].precipitation))
                for k in step.result.available
                if step.points[k].precipitation is not None
            ]
            if samples:
                member_samples[step.lead_hours] = samples

        extreme_events = extreme_detector.detect(
            location_name=info.name,
            forecast_points=blended_points,
            member_samples=member_samples,
        )

        # --- Explainability from measured sensitivities --------------------
        display_step = next(
            (s for s in steps if s.lead_hours == weights.leadTimeHours), steps[0]
        )
        explainability = explainability_engine.explain(
            weights=weights,
            regime=regime,
            disagreement=disagreement,
            feature_vector=display_step.feature_vector,
            lead_time_hours=weights.leadTimeHours,
        )

        now_utc = datetime.now(timezone.utc)
        data_quality = "DEGRADED" if unavailable else "OK"
        status_basis = (
            f"gating network {gating_manager.status}"
            f" ({weights.basis.replace('_', ' ')})"
        )
        # The previous code always prefixed "ONLINE", including when a model was
        # silently missing, which is exactly the case an operator needs to see.
        status_label = "DEGRADED" if unavailable else "ONLINE"

        response = BlendedForecastResponse(
            location=info,
            generatedAt=now_utc.isoformat().replace("+00:00", "Z"),
            status=f"{status_label} - {status_basis}",
            dataQuality=data_quality,
            statusDetail=status_detail,
            availableModels=available,
            unavailableModels=unavailable,
            gatingNetworkStatus=gating_manager.status,
            weightBasis=weights.basis,
            activeRegime=regime,
            disagreement=disagreement,
            weights=weights,
            currentBlend=self._pick_current_point(blended_points),
            hourlyTrajectory=blended_points,
            modelForecasts=model_forecasts,
            extremeEvents=extreme_events,
            explainability=explainability,
        )

        if db is not None:
            await self._persist(
                db,
                response=response,
                matched_id=matched_id,
                location=info,
                model_forecasts=model_forecasts,
                available=available,
            )

        logger.info(
            "blended forecast generated",
            extra={
                "context": {
                    "lat": latitude,
                    "lon": longitude,
                    "models": available,
                    "steps": len(blended_points),
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                }
            },
        )
        return response

    # -- helpers -------------------------------------------------------------

    async def _fetch(self, latitude: float, longitude: float):
        return await open_meteo_provider.fetch_forecast_with_elevation(
            latitude, longitude, settings.FORECAST_DAYS
        )

    @staticmethod
    def _accumulate(
        model_forecasts: Dict[str, List], available: List[str], hours: int
    ) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for key in available:
            points = model_forecasts[key][:hours]
            values = [p.precipitation for p in points if p.precipitation is not None]
            if values:
                out[key] = float(sum(values))
        return out

    @staticmethod
    def _pick_current(model_forecasts: Dict[str, List], available: List[str]):
        """The member step whose valid time is nearest to now.

        Index 0 of the array is midnight, not the current hour, so the previous
        code labelled a 6-hour-old reading as 'current conditions'.
        """
        best = None
        best_delta = None
        for key in available:
            for point in model_forecasts[key]:
                if point.temperature is None:
                    continue
                delta = abs(point.leadTimeHours)
                if best_delta is None or delta < best_delta:
                    best, best_delta = point, delta
        return best

    @staticmethod
    def _pick_current_point(
        points: List[BlendedForecastPoint],
    ) -> Optional[BlendedForecastPoint]:
        if not points:
            return None
        return min(points, key=lambda p: abs(p.leadTimeHours))

    @staticmethod
    def _member_at(model_forecasts: Dict[str, List], key: str, valid_time: str):
        """The same-model point on the same valid time as the picked step.

        Indexing ``model_forecasts[k][0]`` reads midnight of day one, so the
        regime was being classified from a stale step while the response
        claimed to describe current conditions.
        """
        for point in model_forecasts.get(key, []):
            if (point.validTime or point.timestamp) == valid_time:
                return point
        return None

    def _classify(self, model_forecasts, available, current_pt, member_24h, info) -> WeatherRegime:
        valid_time = current_pt.validTime or current_pt.timestamp

        aligned: Dict[str, object] = {}
        for key in available:
            point = self._member_at(model_forecasts, key, valid_time)
            if point is not None:
                aligned[key] = point

        def mean_of(attr: str) -> float:
            values = [
                getattr(p, attr) for p in aligned.values() if getattr(p, attr) is not None
            ]
            return float(sum(values) / len(values)) if values else 0.0

        # 24 h accumulation is averaged over every contributing member, not
        # taken from whichever model happened to be first in the list.
        rain_24h = (
            float(sum(member_24h.values()) / len(member_24h)) if member_24h else 0.0
        )

        return regime_classifier.classify(
            latitude=info.latitude,
            longitude=info.longitude,
            elevation=float(info.elevation or 0.0),
            temperature=mean_of("temperature"),
            humidity=mean_of("humidity"),
            pressure=mean_of("pressure"),
            wind_speed=mean_of("windSpeed"),
            precipitation=float(current_pt.precipitation or 0.0),
            precipitation_24h=rain_24h,
            timestamp_str=valid_time,
        )

    def _vector_for(self, step, latitude, longitude, elevation, regime):
        """Kept for callers that hold a step without its retained vector."""
        from app.features.engineer import feature_engineer

        return feature_engineer.extract_features(
            latitude=latitude,
            longitude=longitude,
            elevation=elevation,
            timestamp_str=step.timestamp,
            lead_time_hours=step.lead_hours,
            model_forecasts={
                k: {
                    "temperature": p.temperature,
                    "humidity": p.humidity,
                    "pressure": p.pressure,
                    "windSpeed": p.windSpeed,
                    "precipitation": p.precipitation,
                    "dewPoint": p.dewPoint,
                }
                for k, p in step.points.items()
            },
            active_regime=regime.regime,
        )

    def _unavailable_response(
        self,
        latitude: float,
        longitude: float,
        location_name: Optional[str],
        detail: str,
    ) -> BlendedForecastResponse:
        """A truthful empty response. Never invents weather values."""
        from app.schemas.weather import (
            ExplainabilityReport,
            LocationInfo,
            ModelDisagreement,
            WeightDistribution,
            WeatherRegime,
        )

        now = datetime.now(timezone.utc)

        return BlendedForecastResponse(
            location=LocationInfo(
                name=location_name or f"{latitude:.4f}, {longitude:.4f}",
                latitude=latitude,
                longitude=longitude,
                elevation=0.0,
                elevationSource="unavailable",
            ),
            generatedAt=now.isoformat().replace("+00:00", "Z"),
            status="UNAVAILABLE - no upstream data",
            dataQuality="UNAVAILABLE",
            statusDetail=detail,
            availableModels=[],
            unavailableModels=list(MODEL_KEYS),
            gatingNetworkStatus=gating_manager.status,
            weightBasis="physical_prior",
            activeRegime=WeatherRegime(
                regime="UNKNOWN",
                confidence=0.0,
                synopticCluster="unclassified",
                convectiveIndex=0.0,
                orographicIndex=0.0,
                description="Regime could not be classified: no upstream data.",
            ),
            disagreement=ModelDisagreement(
                variable="rainfall",
                mean=0.0, min=0.0, max=0.0, range=0.0, stdDev=0.0,
                spreadLevel="INSUFFICIENT_MODELS",
                description="No model data available.",
                sampleCount=0,
                thresholdBasis="n/a",
            ),
            weights=WeightDistribution(
                variable="temperature",
                leadTimeHours=24,
                weights=[],
                sumWeights=0.0,
                dominantModel="None",
                availableModels=[],
                basis="physical_prior",
            ),
            currentBlend=None,
            hourlyTrajectory=[],
            modelForecasts={},
            extremeEvents=[],
            explainability=ExplainabilityReport(
                summary="No forecast was produced.",
                coherenceIndex=0.0,
                attributions=[],
                dominantModelRationale=detail,
                method="not applicable",
                basedOnTrainedModel=gating_manager.status == "TRAINED",
            ),
        )

    # -- persistence ---------------------------------------------------------

    async def _persist(
        self,
        db: AsyncSession,
        *,
        response: BlendedForecastResponse,
        matched_id: Optional[int],
        location,
        model_forecasts,
        available: List[str],
    ) -> None:
        """Persist the run, the member forecasts and the blended output.

        The previous implementation created a ForecastRun, a regime record, a
        disagreement record and weight rows, but never wrote ForecastValue or
        BlendedForecast. That is why no real verification data ever existed and
        the verification report had to be hardcoded.
        """
        try:
            location_id = await location_resolver.ensure_persisted(db, location)
        except Exception as exc:
            await db.rollback()
            logger.warning(
                "forecast persistence aborted before location lookup",
                extra={"context": {"error": str(exc)}},
            )
            return

        try:
            now_utc = datetime.now(timezone.utc)
            run = ForecastRun(
                location_id=location_id,
                run_timestamp=now_utc,
                model_cycle=now_utc.strftime("%Y-%m-%dT%HZ"),
                available_models=",".join(available),
                data_quality=response.dataQuality,
            )
            db.add(run)
            await db.flush()

            db.add(
                WeatherRegimeRecord(
                    run_id=run.id,
                    regime_name=response.activeRegime.regime,
                    confidence=response.activeRegime.confidence,
                    synoptic_cluster=response.activeRegime.synopticCluster,
                )
            )
            db.add(
                DisagreementRecord(
                    run_id=run.id,
                    variable=response.disagreement.variable,
                    spread_mean=response.disagreement.mean,
                    spread_std=response.disagreement.stdDev,
                    spread_range=response.disagreement.range,
                    spread_level=response.disagreement.spreadLevel,
                    sample_count=response.disagreement.sampleCount,
                )
            )
            for w in response.weights.weights:
                db.add(
                    ModelWeightEntity(
                        run_id=run.id,
                        variable=response.weights.variable,
                        lead_time_hours=response.weights.leadTimeHours,
                        model_name=w.modelName,
                        weight=w.weight,
                        available=w.available,
                    )
                )

            for event in response.extremeEvents:
                db.add(
                    ExtremeEventRecord(
                        run_id=run.id,
                        event_type=event.eventType,
                        severity=event.severity,
                        intensity=event.intensityValue,
                        unit=event.unit,
                        trigger_time=event.time,
                        lead_time_hours=event.leadTimeHours,
                        model_agreement=event.modelAgreement,
                        details=event.details,
                    )
                )

            for model in available:
                for point in model_forecasts[model][:settings.FORECAST_DAYS * 24]:
                    db.add(
                        ForecastValue(
                            run_id=run.id,
                            model_name=model,
                            timestamp=point.timestamp,
                            lead_time_hours=point.leadTimeHours,
                            temperature=point.temperature,
                            humidity=point.humidity,
                            pressure=point.pressure,
                            wind_speed=point.windSpeed,
                            wind_direction=point.windDirection,
                            precipitation=point.precipitation,
                            cloud_cover=point.cloudCover,
                            weather_code=point.weatherCode,
                        )
                    )

            for point in response.hourlyTrajectory:
                db.add(
                    BlendedForecast(
                        run_id=run.id,
                        timestamp=point.timestamp,
                        lead_time_hours=point.leadTimeHours,
                        temperature=point.temperature,
                        precipitation=point.precipitation,
                        wind_speed=point.windSpeed,
                        humidity=point.humidity,
                        pressure=point.pressure,
                        dominant_model=point.dominantSource,
                        confidence=point.confidencePercentage or 0.0,
                        contributing_models=",".join(available),
                    )
                )

            await db.commit()
        except Exception as exc:
            # Roll back so a failed write cannot poison the session for the
            # caller, and log rather than printing and swallowing.
            await db.rollback()
            logger.warning(
                "forecast persistence failed",
                extra={"context": {"error": str(exc), "run_location": location_id}},
            )


forecast_service = ForecastService()

