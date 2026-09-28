from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.session import Base


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    elevation = Column(Float, default=0.0)
    country = Column(String(50), default="India")
    admin1 = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_locations_coords", "latitude", "longitude"),)


class ForecastRun(Base):
    __tablename__ = "forecast_runs"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    run_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    model_cycle = Column(String(24), default="00Z")
    # Models that actually carried data for this run, JSON-encoded.
    available_models = Column(Text, nullable=True)
    data_quality = Column(String(16), default="OK")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ForecastValue(Base):
    """A single model's forecast at a single timestep for a single run."""

    __tablename__ = "forecast_values"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("forecast_runs.id"), nullable=False, index=True)
    model_name = Column(String(50), nullable=False, index=True)
    timestamp = Column(String(24), nullable=False, index=True)
    lead_time_hours = Column(Integer, nullable=False)
    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)
    dew_point = Column(Float, nullable=True)
    pressure = Column(Float, nullable=True)
    wind_speed = Column(Float, nullable=True)
    wind_direction = Column(Float, nullable=True)
    precipitation = Column(Float, nullable=True)
    cloud_cover = Column(Float, nullable=True)
    weather_code = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_forecast_values_lookup", "run_id", "model_name", "timestamp"),
        Index("ix_forecast_values_valid", "model_name", "timestamp", "lead_time_hours"),
    )


class BlendedForecast(Base):
    __tablename__ = "blended_forecasts"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("forecast_runs.id"), nullable=False, index=True)
    timestamp = Column(String(24), nullable=False, index=True)
    lead_time_hours = Column(Integer, nullable=False)
    temperature = Column(Float, nullable=False)
    precipitation = Column(Float, nullable=False)
    wind_speed = Column(Float, nullable=False)
    humidity = Column(Float, nullable=False)
    pressure = Column(Float, nullable=False)
    dominant_model = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=False)
    contributing_models = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_blended_valid", "run_id", "timestamp"),
        Index("ix_blended_lead", "lead_time_hours"),
    )


class ModelWeightEntity(Base):
    __tablename__ = "model_weights"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("forecast_runs.id"), nullable=False, index=True)
    variable = Column(String(50), nullable=False)
    lead_time_hours = Column(Integer, nullable=False)
    model_name = Column(String(50), nullable=False)
    weight = Column(Float, nullable=False)
    # False when the model carried no data and its weight was masked to zero.
    available = Column(Boolean, default=True)


class WeatherRegimeRecord(Base):
    __tablename__ = "weather_regimes"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("forecast_runs.id"), nullable=False, index=True)
    regime_name = Column(String(32), nullable=False)
    confidence = Column(Float, nullable=False)
    synoptic_cluster = Column(String(120), nullable=False)


class DisagreementRecord(Base):
    __tablename__ = "model_disagreements"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("forecast_runs.id"), nullable=False, index=True)
    variable = Column(String(50), nullable=False)
    spread_mean = Column(Float, nullable=False)
    spread_std = Column(Float, nullable=False)
    spread_range = Column(Float, nullable=False)
    spread_level = Column(String(32), nullable=False)
    sample_count = Column(Integer, default=0)


class ExtremeEventRecord(Base):
    __tablename__ = "extreme_events"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("forecast_runs.id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    intensity = Column(Float, nullable=False)
    unit = Column(String(16), nullable=False, server_default="mm")
    trigger_time = Column(String(24), nullable=False)
    lead_time_hours = Column(Integer, nullable=True)
    model_agreement = Column(Float, nullable=True)
    details = Column(Text, nullable=True)


class WeatherObservation(Base):
    """Verified observation used as the reference for skill scoring."""

    __tablename__ = "weather_observations"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    timestamp = Column(String(24), nullable=False, index=True)
    source = Column(String(50), default="ERA5 reanalysis")
    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)
    pressure = Column(Float, nullable=True)
    wind_speed = Column(Float, nullable=True)
    precipitation = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_observations_lookup", "location_id", "timestamp"),
    )


class VerificationRecord(Base):
    __tablename__ = "verification_results"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    model_name = Column(String(50), nullable=False, index=True)
    variable = Column(String(50), nullable=False)
    lead_time_hours = Column(Integer, nullable=False)
    sample_count = Column(Integer, default=0)
    mae = Column(Float, nullable=False)
    rmse = Column(Float, nullable=False)
    bias = Column(Float, nullable=False)
    correlation_r2 = Column(Float, nullable=True)
    period_start = Column(String(24), nullable=True)
    period_end = Column(String(24), nullable=True)
    reference_dataset = Column(String(80), nullable=True)
    evaluated_at = Column(DateTime(timezone=True), server_default=func.now())


class TrainingRun(Base):
    __tablename__ = "training_runs"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(30), nullable=False)  # TRAINED, TRAINING, NOT_TRAINED, ERROR
    dataset_source = Column(String(120), nullable=True)
    sample_count = Column(Integer, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    train_loss = Column(Float, nullable=True)
    val_loss = Column(Float, nullable=True)
    best_epoch = Column(Integer, nullable=True)
    model_path = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)

