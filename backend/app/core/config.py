from __future__ import annotations

from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute project root. Previously every default path was CWD-relative, so
# launching uvicorn from any directory other than the repo root silently lost
# .env, the SQLite file and the model checkpoint.
BASE_DIR = Path(__file__).resolve().parents[3]


class ModelSpec(BaseModel):
    """Canonical description of a forecast model.

    This is the single source of truth for the supported model set. Previously
    the same list was duplicated in four places and could drift silently.
    """

    key: str
    slug: str
    display_name: str
    model_type: str
    institution: str
    native_resolution: str
    update_cycle: str
    lead_horizon_hours: int


# Ordered -- index 0..3 is the gating network output order.
MODEL_REGISTRY: List[ModelSpec] = [
    ModelSpec(
        key="ECMWF_IFS",
        slug="ecmwf_ifs025",
        display_name="ECMWF IFS (0.25 deg)",
        model_type="Deterministic NWP (hydrostatic)",
        institution="European Centre for Medium-Range Weather Forecasts",
        native_resolution="0.25 deg (~28 km)",
        update_cycle="00Z, 12Z",
        lead_horizon_hours=240,
    ),
    ModelSpec(
        key="ECMWF_AIFS",
        slug="ecmwf_aifs025",
        display_name="ECMWF AIFS (0.25 deg, neural)",
        model_type="Data-driven neural NWP",
        institution="ECMWF Machine Learning Team",
        native_resolution="0.25 deg (~28 km)",
        update_cycle="00Z, 12Z",
        lead_horizon_hours=360,
    ),
    ModelSpec(
        key="NOAA_GFS",
        slug="gfs_seamless",
        display_name="NOAA GFS v16.3 (FV3)",
        model_type="Deterministic NWP (spectral dynamical core)",
        institution="NOAA / NCEP",
        native_resolution="0.25 deg (~28 km)",
        update_cycle="00Z, 06Z, 12Z, 18Z",
        lead_horizon_hours=384,
    ),
    ModelSpec(
        key="DWD_ICON",
        slug="icon_seamless",
        display_name="DWD ICON Global",
        model_type="Icosahedral non-hydrostatic NWP",
        institution="Deutscher Wetterdienst",
        native_resolution="0.125 deg (~13 km)",
        update_cycle="00Z, 06Z, 12Z, 18Z",
        lead_horizon_hours=180,
    ),
]

MODEL_KEYS: List[str] = [m.key for m in MODEL_REGISTRY]
SLUG_TO_KEY: dict[str, str] = {m.slug: m.key for m in MODEL_REGISTRY}
KEY_TO_SPEC: dict[str, ModelSpec] = {m.key: m for m in MODEL_REGISTRY}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "AeroBlend AI"
    VERSION: str = "5.0.0"
    API_V1_STR: str = "/api"

    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = True

    # --- Database -----------------------------------------------------------
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR / 'backend' / 'data' / 'aeroblend.db'}"

    # --- External services --------------------------------------------------
    OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com/v1"
    OPEN_METEO_ARCHIVE_URL: str = "https://archive-api.open-meteo.com/v1"
    # Optional. Raising the Open-Meteo tier is the only way to escape the
    # anonymous rate limit, which the public dashboard can otherwise exhaust.
    OPEN_METEO_API_KEY: str = ""

    HTTP_TIMEOUT_SECONDS: float = 20.0
    HTTP_MAX_RETRIES: int = 3
    HTTP_MAX_CONNECTIONS: int = 20
    CACHE_MAX_ENTRIES: int = 256
    WEATHER_CACHE_TTL: int = 1800
    ARCHIVE_CACHE_TTL: int = 86400

    # --- ML / blending ------------------------------------------------------
    MODEL_WEIGHTS_PATH: Path = BASE_DIR / "backend" / "data" / "gating_network.pt"
    GATING_INPUT_DIM: int = 19
    # Device is pinned to CPU. Silently falling back to CPU is fine; silently
    # claiming a GPU that is not present is not.
    ML_DEVICE: Literal["cpu", "cuda"] = "cpu"

    # --- Forecast horizon ---------------------------------------------------
    FORECAST_DAYS: int = 3
    DEFAULT_LATITUDE: float = 12.9716
    DEFAULT_LONGITUDE: float = 77.5946

    # --- Extreme weather thresholds (IMD / WMO aligned) --------------------
    # NOTE: all *_24H thresholds are daily accumulations, *_MM_1H are hourly.
    EXTREME_RAIN_HEAVY_MM_24H: float = 64.5
    EXTREME_RAIN_VERY_HEAVY_MM_24H: float = 115.5
    EXTREME_RAIN_BURST_MM_1H: float = 40.0
    EXTREME_HEAT_TEMP_C: float = 40.0
    EXTREME_WIND_SPEED_KMH: float = 45.0

    # --- Disagreement thresholds (mm on the 24h accumulation) ---------------
    DISAGREEMENT_LOW_MM: float = 2.5
    DISAGREEMENT_HIGH_MM: float = 6.0
    # Below this many contributing models the spread statistic is not
    # meaningful and must not be reported as LOW confidence.
    DISAGREEMENT_MIN_MODELS: int = 3

    # --- Verification -------------------------------------------------------
    VERIFICATION_REFERENCE: str = "ERA5 reanalysis (Open-Meteo archive API)"
    VERIFICATION_WINDOW_DAYS: int = 30
    VERIFICATION_VERIFY_LAG_HOURS: int = 24

    # --- Analogues ----------------------------------------------------------
    ANALOGUE_START_YEAR: int = 1990
    ANALOGUE_CACHE_TTL: int = 7 * 86400

    # --- CORS ---------------------------------------------------------------
    # An explicit allowlist. "*" combined with allow_credentials is both
    # rejected by browsers and unsafe.
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    CORS_ALLOW_CREDENTIALS: bool = False

    # --- Rate limiting ------------------------------------------------------
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


settings = Settings()

