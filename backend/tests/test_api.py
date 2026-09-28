import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app

client = TestClient(app)


def test_health_endpoints():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("HEALTHY", "DEGRADED")

    res_ml = client.get("/health/ml")
    assert res_ml.status_code == 200
    ml = res_ml.json()
    # The checkpoint either exists and is reported as trained, or the endpoint
    # must say so. It must never claim a trained model that is absent.
    assert ml["isTrained"] is True
    assert ml["status"] == "TRAINED"


def test_weather_endpoints():
    res = client.get("/api/weather/models")
    assert res.status_code == 200
    data = res.json()
    assert "models" in data
    assert len(data["models"]) == 4

    res_runs = client.get("/api/weather/model-runs")
    assert res_runs.status_code == 200
    assert "runs" in res_runs.json()


def test_current_weather_masks_unavailable_models():
    res = client.get(
        "/api/weather/current",
        params={"latitude": 12.9716, "longitude": 77.5946},
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("status")

    # weights is a nested distribution object: {variable, leadTimeHours,
    # weights: [...], sumWeights, dominantModel, availableModels, basis}.
    dist = data.get("weights") or {}
    entries = dist.get("weights") or []
    if not entries:
        return

    # AIFS is known to return a null series upstream. If it is reported
    # unavailable it must carry zero weight and no value; claiming a forecast
    # value for it would be fabrication.
    unavailable = set(data.get("unavailableModels") or [])
    for weight in entries:
        if weight.get("modelName") in unavailable:
            assert weight["weight"] == 0.0
            assert weight.get("forecastValue") is None
            assert weight.get("available") is False

    available = [w for w in entries if w.get("available")]
    assert available, "at least one model must be available to report weights"
    assert abs(sum(w["weight"] for w in available) - 1.0) < 1e-3
    assert abs(dist["sumWeights"] - 1.0) < 1e-3
    assert data["dataQuality"] in ("NOMINAL", "DEGRADED")
    if unavailable:
        assert data["dataQuality"] == "DEGRADED"
    assert dist["basis"] in ("gating_network", "physical_prior")


def test_verification_endpoint():
    res = client.get("/api/verification", params={"period_days": 21})
    assert res.status_code == 200
    data = res.json()

    # The previous version of this test asserted overallMae == 1.14 and
    # overallRmse == 1.82. Those were hardcoded UI constants, so the test only
    # passed while the endpoint was returning fabricated numbers. Assert the
    # contract instead.
    assert "computed" in data
    if not data["computed"]:
        # A failed verification must say why rather than returning bare zeros.
        assert data.get("unavailableReason")
        assert data["sampleCount"] == 0
        assert data["modelComparisons"] == []
        return

    assert data["sampleCount"] > 0
    assert data["referenceDataset"]
    assert data["referenceNote"]
    assert len(data["modelComparisons"]) >= 2

    names = {m["modelName"] for m in data["modelComparisons"]}
    # The in-sample fixed weighting must not be presented as the deployed model.
    assert "Inverse_Variance" in names
    assert "AeroBlend" not in names
    assert "Persistence" in names

    for m in data["modelComparisons"]:
        assert m["mae"] >= 0
        assert m["rmse"] >= 0
        assert m["sampleCount"] == data["sampleCount"]

    # Persistence at daily-mean aggregation is very strong, so a negative skill
    # score is a legitimate result and must not be clamped to zero.
    assert data["skillScoreVsPersistence"] <= 1.0 + 1e-9


def test_verification_lead_zero_is_honoured():
    """lead_time_hours=0 must not be silently replaced by the configured default.

    ``lead = lead_time_hours or default`` swallowed a legitimate 0, so an
    analysis-time request was scored as a 24 h lead request.
    """
    res = client.get(
        "/api/verification", params={"period_days": 21, "lead_time_hours": 0}
    )
    assert res.status_code == 200
    assert res.json()["leadTimeHours"] == 0


def test_verification_rejects_bad_variable():
    res = client.get("/api/verification", params={"variable": "pressure"})
    assert res.status_code == 422


def test_historical_analogues_endpoint():
    res = client.get(
        "/api/historical/analogues",
        params={"latitude": 12.9716, "longitude": 77.5946},
    )
    assert res.status_code == 200
    data = res.json()
    assert "matches" in data
    if not data.get("matches"):
        return
    assert len(data["matches"]) >= 1

    sims = [m["similarityPercentage"] for m in data["matches"]]
    # Similarity was collapsing to 0% when the kernel width came from the
    # nearest neighbour; it must now be a spread, non-degenerate value.
    assert max(sims) > min(sims)
    assert all(0.0 <= s <= 100.0 for s in sims)
    for m in data["matches"]:
        assert m["date"]
        assert m.get("synopticMatchName")
        assert m.get("matchedState")
        assert m.get("outcome24h")


def test_rate_limit_headers_present():
    res = client.get("/api/weather/models")
    assert res.status_code == 200
    assert "X-RateLimit-Limit" in res.headers
    assert "X-RateLimit-Remaining" in res.headers


def test_health_does_not_leak_secrets():
    for path in ("/health", "/health/ml", "/health/database", "/health/providers"):
        body = client.get(path).text
        assert "sqlite:///" not in body
        assert ".db" not in body
        assert "password" not in body.lower()
        assert "gating_network.pt" not in body
