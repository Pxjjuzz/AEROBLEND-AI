from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.database.session import get_db
from backend.app.schemas.weather import BlendedForecastResponse, ModelDisagreement
from backend.app.services.forecast_service import forecast_service

router = APIRouter(prefix="/forecast", tags=["Forecast"])


class BlendRequest(BaseModel):
    """Typed request body.

    The old handler took ``Dict[str, Any]``, so an out-of-range latitude or a
    string coordinate reached the provider and failed far from its cause.
    """

    latitude: float = Field(settings.DEFAULT_LATITUDE, ge=-90.0, le=90.0)
    longitude: float = Field(settings.DEFAULT_LONGITUDE, ge=-180.0, le=180.0)
    location_name: str = Field("Bengaluru, Karnataka", max_length=200)


@router.get("/blended", response_model=BlendedForecastResponse)
async def get_blended_forecast(
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


@router.post("/blend", response_model=BlendedForecastResponse)
async def blend_custom_forecast(
    payload: BlendRequest = Body(...),
    db: AsyncSession = Depends(get_db),
) -> BlendedForecastResponse:
    return await forecast_service.get_blended_forecast(
        latitude=payload.latitude,
        longitude=payload.longitude,
        location_name=payload.location_name,
        db=db,
    )


@router.get("/models")
async def get_individual_model_forecasts(
    latitude: float = Query(settings.DEFAULT_LATITUDE, ge=-90.0, le=90.0),
    longitude: float = Query(settings.DEFAULT_LONGITUDE, ge=-180.0, le=180.0),
    location_name: str = Query("Bengaluru, Karnataka"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    resp = await forecast_service.get_blended_forecast(
        latitude=latitude,
        longitude=longitude,
        location_name=location_name,
        db=db,
    )
    return {
        "location": resp.location,
        "models": resp.modelForecasts,
        "availableModels": resp.availableModels,
        "unavailableModels": resp.unavailableModels,
        "dataQuality": resp.dataQuality,
        "generatedAt": resp.generatedAt,
    }


@router.get("/weights")
async def get_forecast_weights(
    latitude: float = Query(settings.DEFAULT_LATITUDE, ge=-90.0, le=90.0),
    longitude: float = Query(settings.DEFAULT_LONGITUDE, ge=-180.0, le=180.0),
    location_name: str = Query("Bengaluru, Karnataka"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    resp = await forecast_service.get_blended_forecast(
        latitude=latitude,
        longitude=longitude,
        location_name=location_name,
        db=db,
    )
    return {
        "weights": resp.weights,
        "weightBasis": resp.weightBasis,
        "dataQuality": resp.dataQuality,
    }


@router.get("/disagreement", response_model=ModelDisagreement)
async def get_model_disagreement(
    latitude: float = Query(settings.DEFAULT_LATITUDE, ge=-90.0, le=90.0),
    longitude: float = Query(settings.DEFAULT_LONGITUDE, ge=-180.0, le=180.0),
    location_name: str = Query("Bengaluru, Karnataka"),
    db: AsyncSession = Depends(get_db),
) -> ModelDisagreement:
    resp = await forecast_service.get_blended_forecast(
        latitude=latitude,
        longitude=longitude,
        location_name=location_name,
        db=db,
    )
    return resp.disagreement
