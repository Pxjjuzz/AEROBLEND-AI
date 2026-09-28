from __future__ import annotations

import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Deque, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp

from backend.app.api.forecast import router as forecast_router
from backend.app.api.health import router as health_router
from backend.app.api.intelligence import router as intelligence_router
from backend.app.api.verification import router as verification_router
from backend.app.api.weather import router as weather_router
from backend.app.blending.gating_network import gating_manager
from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.database.models import Location
from backend.app.database.session import AsyncSessionLocal, dispose_db, init_db
from backend.app.providers.open_meteo import open_meteo_provider
from backend.app.websocket.manager import websocket_manager

logger = get_logger(__name__)

SEED_LOCATIONS = [
    # Elevations are the documented fallback only. The provider's grid
    # elevation wins at runtime; these are used when the upstream field is
    # missing, not as a substitute for it.
    ("Bengaluru, Karnataka", 12.9716, 77.5946, 920.0, "Karnataka"),
    ("Mumbai, Maharashtra", 19.0760, 72.8777, 14.0, "Maharashtra"),
    ("New Delhi, NCR", 28.6139, 77.2090, 216.0, "Delhi"),
    ("Chennai, Tamil Nadu", 13.0827, 80.2707, 6.0, "Tamil Nadu"),
    ("Hyderabad, Telangana", 17.3850, 78.4867, 505.0, "Telangana"),
]


class RateLimitMiddleware:
    """Fixed-window per-client limiter.

    The service was previously completely unauthenticated and unthrottled, so
    one client could exhaust the shared Open-Meteo anonymous quota for
    everyone by repeatedly calling the verification and analogue endpoints.

    Implemented as a raw ASGI callable so it also sees, and can pass through,
    the websocket scope.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._window = float(settings.RATE_LIMIT_WINDOW_SECONDS)
        self._limit = int(settings.RATE_LIMIT_REQUESTS)

    @staticmethod
    def _client_key(scope) -> str:
        client = scope.get("client")
        host = client[0] if client else "unknown"
        # Only trust X-Forwarded-For when a proxy is actually in front of us.
        if settings.is_production:
            for key, value in scope.get("headers") or []:
                if key == b"x-forwarded-for":
                    return value.decode("latin-1").split(",")[0].strip()
        return host

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not settings.RATE_LIMIT_ENABLED:
            await self.app(scope, receive, send)
            return

        key = self._client_key(scope)
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self._window:
            bucket.popleft()

        if len(bucket) >= self._limit:
            logger.warning("rate limit exceeded", extra={"context": {"client": key}})
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Retry after the window resets.",
                    "limit": self._limit,
                    "windowSeconds": int(self._window),
                },
                headers={"Retry-After": str(int(self._window))},
            )
            await response(scope, receive, send)
            return

        bucket.append(now)

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("X-RateLimit-Limit", str(self._limit))
                headers.append(
                    "X-RateLimit-Remaining", str(max(0, self._limit - len(bucket)))
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    try:
        async with AsyncSessionLocal() as session:
            existing = await session.execute(select(Location.id).limit(1))
            if not existing.first():
                session.add_all(
                    Location(
                        name=name,
                        latitude=lat,
                        longitude=lon,
                        elevation=elev,
                        country="India",
                        admin1=admin1,
                    )
                    for name, lat, lon, elev, admin1 in SEED_LOCATIONS
                )
                await session.commit()
    except Exception as exc:  # pragma: no cover - startup must not die on seed
        logger.warning("location seed skipped", extra={"context": {"error": str(exc)}})

    gating_manager.reload_if_changed()
    logger.info(
        "AeroBlend AI backend started",
        extra={"context": {"gatingStatus": gating_manager.status}},
    )

    yield

    # Release pooled resources. Previously the HTTP client, the DB engine pool
    # and the socket registry were all leaked on shutdown, which broke test
    # runs and left sockets open across reloads.
    open_meteo_provider.close()
    await open_meteo_provider.clear_caches()
    await dispose_db()
    logger.info("AeroBlend AI backend shut down cleanly")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Hybrid AI-NWP Multi-Model Forecast Blending System (SIH26081)",
    lifespan=lifespan,
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    # Taken from config rather than hardcoded True. A wildcard origin list with
    # credentials enabled is rejected by browsers and unsafe when it is not.
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)

app.include_router(weather_router, prefix=settings.API_V1_STR)
app.include_router(forecast_router, prefix=settings.API_V1_STR)
app.include_router(intelligence_router, prefix=settings.API_V1_STR)
app.include_router(verification_router, prefix=settings.API_V1_STR)
app.include_router(health_router)


@app.websocket("/ws/forecast")
async def websocket_forecast_endpoint(websocket: WebSocket) -> None:
    await websocket_manager.connect(websocket)
    try:
        await websocket.send_json(
            {
                "type": "CONNECTION_ESTABLISHED",
                "message": "Connected to AeroBlend Operational Weather Stream",
                "serverTime": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "engineVersion": settings.VERSION,
                "gatingNetworkStatus": gating_manager.status,
            }
        )
        while True:
            raw = await websocket.receive_text()
            if len(raw) > 2048:
                # The previous handler echoed the entire client payload back
                # verbatim, which is an unbounded reflection channel.
                await websocket.send_json(
                    {"type": "ERROR", "detail": "message too large (max 2048 bytes)"}
                )
                continue
            await websocket.send_json(
                {
                    "type": "TELEMETRY_ACK",
                    "receivedBytes": len(raw),
                    "timestamp": datetime.now(timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
            )
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("websocket error", extra={"context": {"error": str(exc)}})
        websocket_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
