import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest
import numpy as np
from backend.app.providers.open_meteo import open_meteo_provider
from backend.app.features.engineer import feature_engineer
from backend.app.regimes.classifier import regime_classifier
from backend.app.disagreement.calculator import disagreement_calculator
from backend.app.blending.gating_network import gating_manager
from backend.app.blending.engine import blending_engine
from backend.app.extremes.detector import extreme_detector
from backend.app.verification.evaluator import verification_evaluator
from backend.app.schemas.weather import ForecastPoint, WeatherRegime

def test_uv_wind_calculation():
    # Wind from North (0 deg) blowing south: u = 0, v = -speed
    u, v = open_meteo_provider._calculate_uv_wind(36.0, 0.0)
    assert u == 0.0
    assert abs(v - (-10.0)) < 0.1

    # Wind from West (270 deg) blowing east: u = +speed, v = 0
    u, v = open_meteo_provider._calculate_uv_wind(36.0, 270.0)
    assert abs(u - 10.0) < 0.1
    assert abs(v - 0.0) < 0.1

def test_feature_engineering():
    dummy_models = {
        "ECMWF_IFS": {"temperature": 27.0, "humidity": 75.0, "pressure": 1012.0, "windSpeed": 14.0, "precipitation": 2.5, "dewPoint": 22.0},
        "NOAA_GFS": {"temperature": 26.5, "humidity": 78.0, "pressure": 1011.5, "windSpeed": 12.0, "precipitation": 3.0, "dewPoint": 22.5}
    }
    feats = feature_engineer.extract_features(
        latitude=12.97,
        longitude=77.59,
        elevation=920.0,
        timestamp_str="2026-09-27T12:00:00Z",
        lead_time_hours=24,
        model_forecasts=dummy_models,
        active_regime="CONVECTIVE"
    )
    assert isinstance(feats, np.ndarray)
    assert len(feats) == 19
    # All features normalized within reasonable bounds
    assert not np.isnan(feats).any()

def test_weights_sum_to_one():
    # CRITICAL INVARIANT: sum(weights) = 1.0 within numerical tolerance
    feats = np.zeros(19, dtype=np.float32)
    weights = gating_manager.predict_weights(feats, lead_time_hours=24)
    total_w = sum(weights.values())
    assert abs(total_w - 1.0) < 1e-4
    for m, w in weights.items():
        assert w >= 0.0

def test_regime_classification():
    # Monsoon conditions
    reg_monsoon = regime_classifier.classify(
        latitude=13.0,
        longitude=77.6,
        elevation=920.0,
        temperature=27.0,
        humidity=85.0,
        pressure=1008.0,
        wind_speed=15.0,
        precipitation=8.0,
        timestamp_str="2026-09-16T14:00:00Z"
    )
    assert reg_monsoon.regime in ["MONSOON", "CONVECTIVE"]

    # Extreme storm conditions
    reg_extreme = regime_classifier.classify(
        latitude=13.0,
        longitude=77.6,
        elevation=920.0,
        temperature=28.0,
        humidity=90.0,
        pressure=998.0,
        wind_speed=52.0,
        precipitation=55.0,
        timestamp_str="2026-09-16T14:00:00Z"
    )
    assert reg_extreme.regime == "EXTREME"

def test_disagreement_calculation():
    # Low spread test
    res_low = disagreement_calculator.calculate([10.0, 10.5, 9.8, 10.2], variable_name="rainfall")
    assert res_low.spreadLevel == "LOW"

    # High spread test
    res_high = disagreement_calculator.calculate([2.0, 15.0, 35.0, 8.0], variable_name="rainfall")
    assert res_high.spreadLevel == "HIGH"
    assert res_high.range > 30.0

def test_blending_engine():
    active_reg = WeatherRegime(
        regime="NORMAL",
        confidence=0.9,
        synopticCluster="Cluster #1A",
        convectiveIndex=30.0,
        orographicIndex=40.0,
        description="Normal"
    )
    # Generate 5 timesteps for 2 models
    pts_ifs = [
        ForecastPoint(
            timestamp=f"2026-09-27T0{i}:00:00Z",
            latitude=12.97,
            longitude=77.59,
            temperature=25.0 + i,
            humidity=80.0,
            dewPoint=21.0,
            pressure=1012.0,
            windSpeed=15.0,
            windDirection=270.0,
            windU=4.17,
            windV=0.0,
            precipitation=2.0,
            rain=2.0,
            cloudCover=50.0,
            weatherCode=61,
            modelName="ECMWF_IFS",
            provider="Open-Meteo",
            modelRun="00Z",
            leadTimeHours=i,
            sourceTimestamp="2026-09-27T00:00:00Z"
        ) for i in range(5)
    ]
    pts_gfs = [
        ForecastPoint(
            timestamp=f"2026-09-27T0{i}:00:00Z",
            latitude=12.97,
            longitude=77.59,
            temperature=24.0 + i,
            humidity=75.0,
            dewPoint=20.0,
            pressure=1011.5,
            windSpeed=12.0,
            windDirection=270.0,
            windU=3.33,
            windV=0.0,
            precipitation=1.5,
            rain=1.5,
            cloudCover=40.0,
            weatherCode=61,
            modelName="NOAA_GFS",
            provider="Open-Meteo",
            modelRun="00Z",
            leadTimeHours=i,
            sourceTimestamp="2026-09-27T00:00:00Z"
        ) for i in range(5)
    ]

    model_dict = {"ECMWF_IFS": pts_ifs, "NOAA_GFS": pts_gfs}
    blended, weights, steps = blending_engine.blend(
        latitude=12.97,
        longitude=77.59,
        elevation=920.0,
        model_forecasts=model_dict,
        active_regime=active_reg,
    )
    assert len(blended) == 5
    assert 24.0 <= blended[0].temperature <= 26.0
    assert 1.5 <= blended[0].precipitation <= 2.0
    assert abs(weights.sumWeights - 1.0) < 1e-4

def test_verification_metrics():
    obs = [10.0, 20.0, 30.0, 40.0]
    preds = [12.0, 19.0, 28.0, 42.0]
    metric = verification_evaluator.calculate_metrics(obs, preds, "TestModel", "rainfall", lead_time_hours=24)
    assert metric.mae == 1.75
    # sqrt(13/4) = 1.80277..., reported rounded to 3 dp. The previous exact
    # equality against 1.80 could only ever have passed by accident.
    assert metric.rmse == pytest.approx(1.803, abs=1e-3)
    assert metric.bias == 0.25
    assert metric.correlationR2 > 0.95


def test_weights_mask_unavailable_models():
    # A model with no data must receive exactly zero weight, and the rest must
    # be renormalised. Which available model dominates depends on the trained
    # checkpoint, so assert the invariants, not a specific assignment.
    feats = np.zeros(19, dtype=np.float32)
    all_models = gating_manager.predict_weights(feats, lead_time_hours=24)
    masked = gating_manager.predict_weights(
        feats,
        lead_time_hours=24,
        available_models=["ECMWF_IFS", "NOAA_GFS"],
    )
    assert masked["ECMWF_AIFS"] == 0.0
    assert masked["DWD_ICON"] == 0.0
    assert any(masked[k] > 0.0 for k in ("ECMWF_IFS", "NOAA_GFS"))
    assert all(w >= 0.0 for w in masked.values())
    assert abs(sum(masked.values()) - 1.0) < 1e-4
    assert abs(sum(all_models.values()) - 1.0) < 1e-4
