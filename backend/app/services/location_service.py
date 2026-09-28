from __future__ import annotations

import math
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database.models import Location
from app.schemas.weather import LocationInfo

logger = get_logger(__name__)

# Beyond this distance the nearest seeded city is not a meaningful description
# of the requested point, so the API-derived elevation is used instead.
MATCH_RADIUS_KM = 60.0
EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = p2 - p1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class LocationResolver:
    """Resolve a coordinate to a named location with a real elevation.

    Replaces ``elevation = 920.0 if "Bengaluru" in location_name else 50.0``,
    which fed the gating network and the orographic index a fabricated terrain
    value for every city except Bengaluru, and hardcoded ``location_id = 1`` on
    every persisted forecast run regardless of the requested coordinate.
    """

    def __init__(self) -> None:
        self._cache: dict[Tuple[float, float], Optional[LocationInfo]] = {}

    async def resolve(
        self,
        db: Optional[AsyncSession],
        *,
        latitude: float,
        longitude: float,
        location_name: Optional[str] = None,
        api_elevation: Optional[float] = None,
    ) -> Tuple[LocationInfo, Optional[int]]:
        """Return (location_info, location_id_or_None).

        ``api_elevation`` is the terrain height the forecast API resolved for the
        grid cell, which is the authoritative value for terrain-sensitive
        features. The database elevation is used only when the API omits it.
        """
        key = (round(latitude, 2), round(longitude, 2))
        cached = self._cache.get(key)
        matched: Optional[Location] = None

        if db is not None:
            rows = (
                await db.execute(select(Location).order_by(Location.id).limit(200))
            ).scalars().all()
            best: Optional[Tuple[float, Location]] = None
            for row in rows:
                d = haversine_km(latitude, longitude, row.latitude, row.longitude)
                if best is None or d < best[0]:
                    best = (d, row)
            if best and best[0] <= MATCH_RADIUS_KM:
                matched = best[1]

        if matched is not None and not location_name:
            cached = LocationInfo(
                name=matched.name,
                latitude=latitude,
                longitude=longitude,
                elevation=api_elevation if api_elevation is not None else matched.elevation,
                country=matched.country or "India",
                admin1=matched.admin1,
                timezone="UTC",
                elevationSource="Open-Meteo grid elevation" if api_elevation is not None else "locations table",
            )
            self._cache[key] = cached
            return cached, matched.id

        if cached is not None:
            return cached, matched.id if matched else None

        info = LocationInfo(
            name=location_name or f"{latitude:.4f}, {longitude:.4f}",
            latitude=latitude,
            longitude=longitude,
            elevation=api_elevation if api_elevation is not None else 0.0,
            country="India",
            admin1=None,
            timezone="UTC",
            elevationSource="Open-Meteo grid elevation" if api_elevation is not None else "unknown (flat assumed)",
        )
        self._cache[key] = info
        return info, matched.id if matched else None

    async def ensure_persisted(
        self, db: AsyncSession, info: LocationInfo
    ) -> int:
        """Get or create a Location row so forecasts are not orphaned.

        Previously every ForecastRun was written with ``location_id = 1``,
        which silently attributed all recorded runs to the first seeded city.
        """
        existing = (
            await db.execute(
                select(Location).where(
                    Location.latitude == info.latitude,
                    Location.longitude == info.longitude,
                )
            )
        ).scalars().first()
        if existing:
            return existing.id

        row = Location(
            name=info.name,
            latitude=info.latitude,
            longitude=info.longitude,
            elevation=info.elevation or 0.0,
            country=info.country or "India",
            admin1=info.admin1,
        )
        db.add(row)
        await db.flush()
        return row.id


location_resolver = LocationResolver()

