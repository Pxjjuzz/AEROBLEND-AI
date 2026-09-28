import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import asyncio
from app.services.forecast_service import forecast_service

def test_real_blended_forecast_pipeline():
    async def _run():
        return await forecast_service.get_blended_forecast(
            latitude=12.9716,
            longitude=77.5946,
            location_name="Bengaluru, Karnataka"
        )
    resp = asyncio.run(_run())

    assert resp is not None
    assert resp.location.name == "Bengaluru, Karnataka"
    assert resp.activeRegime.regime in ["NORMAL", "MONSOON", "CONVECTIVE", "EXTREME"]
    assert resp.weights is not None
    assert abs(resp.weights.sumWeights - 1.0) < 1e-3
    assert len(resp.weights.weights) == 4
    assert len(resp.hourlyTrajectory) > 0
    assert resp.currentBlend is not None
    assert resp.explainability is not None
    assert len(resp.explainability.attributions) > 0
    print("Real blended current temp:", resp.currentBlend.temperature, "°C")
    print("Real blended current precip:", resp.currentBlend.precipitation, "mm")
    print("Active regime:", resp.activeRegime.regime)
    print("Dominant model:", resp.weights.dominantModel)
