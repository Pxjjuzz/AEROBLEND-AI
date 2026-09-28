from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.services.forecast_service import forecast_service
from app.analogues.search import analogue_search
from app.database.session import get_db

router = APIRouter(tags=["Intelligence"])

@router.get("/extreme-events")
async def get_extreme_events(
    latitude: float = Query(settings.DEFAULT_LATITUDE, ge=-90.0, le=90.0),
    longitude: float = Query(settings.DEFAULT_LONGITUDE, ge=-180.0, le=180.0),
    location_name: str = Query("Bengaluru, Karnataka"),
    db: AsyncSession = Depends(get_db),
):
    resp = await forecast_service.get_blended_forecast(
        latitude=latitude,
        longitude=longitude,
        location_name=location_name,
        db=db,
    )
    return {
        "location": resp.location,
        "activeRegime": resp.activeRegime,
        "events": resp.extremeEvents,
        "count": len(resp.extremeEvents),
        "dataQuality": resp.dataQuality,
        # "ACTIVE_MONITORING" implied a live hazard feed. Events are derived
        # from forecast fields, so the honest label is the quality flag.
        "status": resp.dataQuality,
    }


@router.get("/explainability")
async def get_explainability(
    latitude: float = Query(settings.DEFAULT_LATITUDE, ge=-90.0, le=90.0),
    longitude: float = Query(settings.DEFAULT_LONGITUDE, ge=-180.0, le=180.0),
    location_name: str = Query("Bengaluru, Karnataka"),
    db: AsyncSession = Depends(get_db),
):
    resp = await forecast_service.get_blended_forecast(
        latitude=latitude,
        longitude=longitude,
        location_name=location_name,
        db=db,
    )
    return {
        "location": resp.location,
        "weights": resp.weights,
        "regime": resp.activeRegime,
        "disagreement": resp.disagreement,
        "explainability": resp.explainability,
        "weightBasis": resp.weightBasis,
        "dataQuality": resp.dataQuality,
    }


@router.get("/historical/analogues")
async def get_historical_analogues(
    latitude: float = Query(settings.DEFAULT_LATITUDE, ge=-90.0, le=90.0),
    longitude: float = Query(settings.DEFAULT_LONGITUDE, ge=-180.0, le=180.0),
    temperature: Optional[float] = Query(
        None, description="Defaults to the current blended temperature."
    ),
    pressure: Optional[float] = Query(
        None,
        description="Defaults to the current blended surface pressure. Note this is "
        "surface, not sea-level, pressure; a sea-level default was meaningless for "
        "inland sites.",
    ),
    humidity: Optional[float] = Query(None),
    wind_speed: Optional[float] = Query(None),
    precipitation: Optional[float] = Query(
        None, description="Defaults to the 24 h accumulated blended rainfall."
    ),
    top_k: int = Query(5, ge=1, le=25),
    start_year: int = Query(settings.ANALOGUE_START_YEAR, ge=1940, le=2100),
    db: AsyncSession = Depends(get_db),
):
    """Real ERA5 nearest-neighbour search.

    The previous response hardcoded
    ``"vectorSimilarityMethod": "Topological Cosine Nearest-Neighbor in
    Geopotential Space"`` and a ``"searchDatabase"`` string, then returned
    three fixed records. The method label and the archive it searched are now
    reported from the search that actually ran.

    When the query state is omitted it is taken from the live blended
    forecast, so the search compares like with like instead of matching a
    hardcoded sea-level state against inland surface conditions.
    """
    resp = await forecast_service.get_blended_forecast(
        latitude=latitude,
        longitude=longitude,
        location_name=f"{latitude:.4f}, {longitude:.4f}",
        db=db,
    )

    current = resp.currentBlend
    if current is None:
        return analogue_search._empty(
            latitude,
            longitude,
            None,
            None,
            "no current forecast available to seed the analogue query",
        )

    resolved = {
        "temperature": temperature if temperature is not None else current.temperature,
        "pressure": pressure if pressure is not None else current.pressure,
        "humidity": humidity if humidity is not None else current.humidity,
        "wind_speed": wind_speed if wind_speed is not None else current.windSpeed,
        "precipitation": (
            precipitation
            if precipitation is not None
            else sum(p.precipitation for p in resp.hourlyTrajectory[:24])
        ),
    }

    result = await analogue_search.find_analogues(
        latitude=latitude,
        longitude=longitude,
        top_k=top_k,
        start_year=start_year,
        **resolved,
    )
    return {**result.model_dump(mode="json"), "queryState": resolved}

