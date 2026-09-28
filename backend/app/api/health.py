from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.blending.gating_network import gating_manager
from app.core.config import settings
from app.core.logging import get_logger
from app.database.session import get_db
from app.providers.open_meteo import open_meteo_provider

logger = get_logger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    return {
        "status": "HEALTHY",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.APP_ENV,
    }


@router.get("/health/providers")
async def provider_health() -> Dict[str, Any]:
    health_list = await open_meteo_provider.check_health()
    available = [h for h in health_list if h.status == "OPERATIONAL"]
    return {
        # "DEGRADED" when any configured model is not actually returning data,
        # which is the case for ecmwf_aifs025.
        "overallStatus": (
            "OPERATIONAL" if len(available) == len(health_list) else "DEGRADED"
        ),
        "operationalModels": [h.model for h in available],
        "unavailableModels": [h.model for h in health_list if h.status != "OPERATIONAL"],
        "providers": health_list,
    }


@router.get("/health/database")
async def database_health(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    try:
        await db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # The full exception previously went into the response body, which
        # leaks the DSN, host and driver internals to any unauthenticated
        # caller. Log it server-side, return only a class of failure.
        logger.warning(
            "database health check failed",
            extra={"context": {"error_type": type(exc).__name__}},
        )
        return {"status": "UNAVAILABLE", "dialect": "unknown"}
    # Previously returned the raw connection string.
    return {"status": "CONNECTED"}


@router.get("/health/ml")
async def ml_model_health() -> Dict[str, Any]:
    return {
        "modelName": "AdaptiveGatingNetwork",
        "status": gating_manager.status,
        # The absolute filesystem path of the checkpoint was exposed before.
        "checkpointPresent": os.path.exists(gating_manager.model_path),
        "device": str(gating_manager.device),
        "supportedModels": gating_manager.model_names,
        "isTrained": gating_manager.status == "TRAINED",
        "inputDimensions": settings.GATING_INPUT_DIM,
        "notes": gating_manager.notes,
    }

