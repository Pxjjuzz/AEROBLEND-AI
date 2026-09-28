from __future__ import annotations

from fastapi import APIRouter, Query

from backend.app.core.config import settings
from backend.app.verification.evaluator import verification_evaluator

router = APIRouter(prefix="/verification", tags=["Verification"])


@router.get("")
async def get_verification_report(
    latitude: float = Query(settings.DEFAULT_LATITUDE, ge=-90.0, le=90.0),
    longitude: float = Query(settings.DEFAULT_LONGITUDE, ge=-180.0, le=180.0),
    location_name: str = Query("Bengaluru, Karnataka"),
    period_days: int = Query(
        settings.VERIFICATION_WINDOW_DAYS, ge=7, le=365,
        description="Length of the ERA5 window ending at the verification lag.",
    ),
    variable: str = Query("temperature", pattern="^(temperature|precipitation)$"),
    lead_time_hours: int = Query(
        settings.VERIFICATION_VERIFY_LAG_HOURS, ge=0, le=240,
    ),
):
    """Computed skill scores against ERA5 reanalysis.

    Every number in the response is derived from archived data. When the
    archive cannot be reached the report comes back with ``computed: false``
    and zero sample count rather than plausible-looking placeholders.
    """
    return await verification_evaluator.generate_benchmark_report(
        latitude=latitude,
        longitude=longitude,
        location_name=location_name,
        period_days=period_days,
        variable=variable,
        lead_time_hours=lead_time_hours,
    )


@router.post("/run")
async def trigger_verification_run(
    latitude: float = Query(settings.DEFAULT_LATITUDE, ge=-90.0, le=90.0),
    longitude: float = Query(settings.DEFAULT_LONGITUDE, ge=-180.0, le=180.0),
    location_name: str = Query("Bengaluru, Karnataka"),
    period_days: int = Query(settings.VERIFICATION_WINDOW_DAYS, ge=7, le=365),
    variable: str = Query("temperature", pattern="^(temperature|precipitation)$"),
    lead_time_hours: int = Query(
        settings.VERIFICATION_VERIFY_LAG_HOURS, ge=0, le=240
    ),
):
    report = await verification_evaluator.generate_benchmark_report(
        latitude=latitude,
        longitude=longitude,
        location_name=location_name,
        period_days=period_days,
        variable=variable,
        lead_time_hours=lead_time_hours,
    )
    # The old handler returned status "COMPLETED" unconditionally, including
    # when nothing had been computed.
    return {
        "status": "COMPLETED" if report.computed else "FAILED",
        "sampleCount": report.sampleCount,
        "referenceDataset": report.referenceDataset,
        "report": report,
    }
