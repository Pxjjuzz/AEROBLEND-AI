from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import MODEL_KEYS, MODEL_REGISTRY, KEY_TO_SPEC, settings
from app.database.session import get_db
from app.providers.open_meteo import open_meteo_provider
from app.schemas.weather import BlendedForecastResponse
from app.services.forecast_service import forecast_service

router = APIRouter(prefix="/weather", tags=["Weather"])


@router.get("/locations/search")
async def search_locations(
    query: str = Query(..., min_length=2, max_length=120),
    count: int = Query(8, ge=1, le=20),
) -> Dict[str, Any]:
    """Return live geocoding matches that can be used by every dashboard view."""
    try:
        return {"results": await open_meteo_provider.search_locations(query.strip(), count)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Location search is temporarily unavailable") from exc


@router.get("/current")
async def get_current_weather(
    latitude: float = Query(settings.DEFAULT_LATITUDE, ge=-90.0, le=90.0),
    longitude: float = Query(settings.DEFAULT_LONGITUDE, ge=-180.0, le=180.0),
    location_name: str = Query("Bengaluru, Karnataka"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    resp: BlendedForecastResponse = await forecast_service.get_blended_forecast(
        latitude=latitude,
        longitude=longitude,
        location_name=location_name,
        db=db,
    )
    return {
        "location": resp.location,
        "current": resp.currentBlend,
        "activeRegime": resp.activeRegime,
        "disagreement": resp.disagreement,
        "weights": resp.weights,
        "explainability": resp.explainability,
        "extremeEvents": resp.extremeEvents,
        "dataQuality": resp.dataQuality,
        "availableModels": resp.availableModels,
        "unavailableModels": resp.unavailableModels,
        "weightBasis": resp.weightBasis,
        "status": resp.status,
        "generatedAt": resp.generatedAt,
    }


@router.get("/forecast", response_model=BlendedForecastResponse)
async def get_weather_forecast(
    latitude: float = Query(settings.DEFAULT_LATITUDE, ge=-90.0, le=90.0),
    longitude: float = Query(settings.DEFAULT_LONGITUDE, ge=-180.0, le=180.0),
    location_name: str = Query("Bengaluru, Karnataka"),
    db: AsyncSession = Depends(get_db),
) -> BlendedForecastResponse:
    return await forecast_service.get_blended_forecast(
        latitude=latitude,
        longitude=longitude,
        location_name=location_name,
        db=db,
    )


@router.get("/models")
async def get_available_models() -> Dict[str, Any]:
    """Model catalogue from the single registry, with live availability.

    The previous version returned a hand-maintained list that had drifted from
    the code (it advertised IFS at 0.1 deg / HRES and reported every model,
    including the empty AIFS slug, as OPERATIONAL with no live check).
    """
    health = await open_meteo_provider.check_health()
    health_by_model = {h.model: h for h in health}

    return {
        "models": [
            {
                "id": spec.key,
                "name": spec.display_name,
                "type": spec.model_type,
                "institution": spec.institution,
                "gridResolution": spec.native_resolution,
                "updateCycle": spec.update_cycle,
                "leadHorizonHours": spec.lead_horizon_hours,
                "status": health_by_model[spec.key].status
                if spec.key in health_by_model
                else "UNKNOWN",
                "error": health_by_model[spec.key].error if spec.key in health_by_model else None,
            }
            for spec in MODEL_REGISTRY
        ]
    }


@router.get("/model-runs")
async def get_model_runs() -> Dict[str, Any]:
    """Latest operational cycle per model, derived from each model's cycle.

    The previous response returned four hardcoded rows with a fixed
    "2026-09-27" date and status COMPLETED regardless of the real state.
    """
    now = datetime.now(timezone.utc)
    runs = []
    for key in MODEL_KEYS:
        spec = KEY_TO_SPEC[key]
        cycle_hours = 12 if key in ("ECMWF_IFS", "ECMWF_AIFS") else 6
        latest = now.replace(minute=0, second=0, microsecond=0)
        latest = latest.replace(hour=(latest.hour // cycle_hours) * cycle_hours)
        runs.append(
            {
                "model": key,
                "cycle": f"{latest:%Y-%m-%dT}{latest.hour:02d}Z",
                "status": "EXPECTED",
                "leadHorizonHours": spec.lead_horizon_hours,
                "updateCycle": spec.update_cycle,
            }
        )
    return {
        "generatedAt": now.isoformat().replace("+00:00", "Z"),
        "runs": runs,
    }

