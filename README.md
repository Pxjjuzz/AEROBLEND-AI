# AeroBlend AI — Hybrid AI–NWP Multi-Model Forecast Blending System

[![SIH Problem Statement](https://img.shields.io/badge/SIH-SIH26081-blue.svg)](https://sih.gov.in)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.133+-009688.svg)](https://fastapi.tiangolo.com)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.14+-EE4C2C.svg)](https://pytorch.org)
[![Next.js](https://img.shields.io/badge/Next.js-14.2+-black.svg)](https://nextjs.org)
[![Tailwind CSS](https://img.shields.io/badge/TailwindCSS-Liquid_Glass-38B2AC.svg)](https://tailwindcss.com)

AeroBlend AI is an operational meteorological intelligence platform developed for **SIH Problem Statement SIH26081**. It combines Numerical Weather Prediction (NWP) models and AI weather neural models using an adaptive deep learning gating network that dynamically allocates weights based on geographic location, atmospheric state, diurnal cycles, weather regime, lead time, and inter-model disagreement.

---

## 1. Visual Source of Truth: Google Stitch Design

The entire UI/UX follows the approved Google Stitch design specification:
- **Stitch Project ID:** `7401513429137851547`
- **Visual Aesthetic:** **Premium Light Liquid Glass**
  - Translucent frosted glass panels (`backdrop-blur-xl`, `backdrop-blur-2xl`)
  - Atmospheric blurred background gradients (Electric Cobalt, Cyan, Violet ribbons)
  - Inter typography with Material Symbols Outlined icons
  - Dedicated interactive views: **Overview**, **Forecast & Adaptive Blending**, **Interactive Live 3D Globe**, **Analytics & Verification**, **Models Registry**, **Extreme Weather Events**, **Alerts**, **Data Sources**, and **Settings**.

---

## 2. Core Operational Pipeline

```
REAL WEATHER / NWP SOURCES (ECMWF IFS, AIFS Neural, NOAA GFS, DWD ICON)
                     ↓
             DATA INGESTION
                     ↓
        VALIDATION & NORMALIZATION (ForecastPoint schema, UV wind vectors)
                     ↓
          FEATURE ENGINEERING (19-dimensional spatial & cyclical tensor)
                     ↓
          WEATHER REGIME DETECTION (Normal, Monsoon, Convective, Extreme)
                     ↓
        INTER-MODEL DISAGREEMENT & BIFURCATION CALCULATION
                     ↓
       DEEP LEARNING ADAPTIVE GATING NETWORK (PyTorch Softmax)
                     ↓
         DYNAMIC MODEL WEIGHTS (Strict Invariant: ∑ w_i = 1.0)
                     ↓
      MOMENTUM-CONSERVING DYNAMICALLY BLENDED FORECAST
                     ↓
     CONFIDENCE & UNCERTAINTY BOUNDS (90% Confidence Interval)
                     ↓
         EXTREME WEATHER HAZARD DETECTION (Rain, Wind, Heat)
                     ↓
    EXPLAINABLE AI ENGINE (Physics & Weight Attribution Rationale)
                     ↓
    HISTORICAL ANALOGUES SEARCH (ERA5 Reanalysis 40-Year Match)
                     ↓
  SCIENTIFIC VERIFICATION & BENCHMARKING (MAE, RMSE, Bias, Skill Score)
                     ↓
     FRONTEND VISUALIZATION & INTERACTIVE 3D DIGITAL TWIN GLOBE
```

---

## 3. Real Weather / NWP Providers

AeroBlend AI connects to live publicly available meteorological APIs without synthetic, mock, or randomized data:

1. **ECMWF IFS (0.1° HRES):** Hydrostatic Integrated Forecasting System (~11 km grid).
2. **ECMWF AIFS (0.25°):** ECMWF Machine Learning data-driven neural weather prediction model.
3. **NOAA GFS v16.3:** Global Forecast System with FV3 spectral dynamical core (~28 km).
4. **DWD ICON Global:** Icosahedral Non-hydrostatic model from the German Weather Service (~13 km).
5. **ECMWF ERA5 Reanalysis Archive:** 40+ years of high-resolution atmospheric records for verification and topological analogue search.

---

## 4. Deep Learning Adaptive Blending Engine

Unlike static averaging, AeroBlend AI trains an operational **PyTorch Gating Network** (`AdaptiveGatingNetwork`):
- **Input Tensor (19 dimensions):**
  - Spatial: `latitude`, `longitude`, `elevation`
  - Diurnal & Seasonal: `hour_sin`, `hour_cos`, `month_sin`, `month_cos`
  - Forecast Horizon: `lead_time_hours`
  - Atmospheric Thermodynamics: `temperature`, `humidity`, `pressure`, `wind_speed`, `dew_point_depression`
  - Inter-model Dispersions: `precip_std`, `temp_std`
  - Synoptic Regimes: `regime_convective`, `regime_monsoon`, `regime_extreme`
- **Output:** Softmax weight vector over `[ECMWF_IFS, ECMWF_AIFS, NOAA_GFS, DWD_ICON]`.
- **Mathematical Invariant:**
  $$\sum_{i=1}^{M} w_i = 1.0 \quad \text{and} \quad w_i \ge 0$$
- **Wind Conservation:** Blends horizontal $U$ and $V$ wind components directly to maintain atmospheric angular momentum before synthesizing final wind speed and direction:
  $$U_{\text{blend}} = \sum w_i U_i, \quad V_{\text{blend}} = \sum w_i V_i$$
  $$\text{Speed} = \sqrt{U_{\text{blend}}^2 + V_{\text{blend}}^2} \times 3.6, \quad \text{Direction} = (\text{atan2}(-U_{\text{blend}}, -V_{\text{blend}}) + 360^\circ) \pmod{360^\circ}$$

---

## 5. Project Directory Structure

```
AEROBLEND-AI/
├── backend/
│   ├── app/
│   │   ├── api/             # REST Routers (weather, forecast, intelligence, verification, health)
│   │   ├── core/            # Configuration & Settings
│   │   ├── database/        # SQLAlchemy Async Models & Sessions
│   │   ├── schemas/         # Pydantic Schemas (ForecastPoint, Weights, Regimes, Extremes)
│   │   ├── providers/       # BaseProvider & OpenMeteoProvider
│   │   ├── features/        # 19-dim Feature Extraction Pipeline
│   │   ├── regimes/         # Atmospheric Regime Classifier (Normal, Monsoon, Convective, Extreme)
│   │   ├── disagreement/    # Model Variance & Bifurcation Detector
│   │   ├── blending/        # PyTorch Gating Network & Vector Momentum Blending
│   │   ├── extremes/        # Extreme Weather Detector (Heavy Rain, Gale Winds, Heatwave)
│   │   ├── explainability/  # XAI Attribution Engine ("Why This Forecast?")
│   │   ├── verification/    # Forecast Verification Engine (MAE, RMSE, Bias, Skill Score)
│   │   ├── analogues/       # ERA5 Historical Topological Analogue Search
│   │   ├── websocket/       # WebSocket Manager for Real-Time Streaming
│   │   └── main.py          # FastAPI Application Entrypoint
│   ├── data/                # Checkpoints (gating_network.pt) & SQLite DB
│   ├── scripts/             # train_blender.py (ML Training Pipeline)
│   └── tests/               # Pytest Suite (Unit, Invariants, API, Live Pipeline)
├── frontend/
│   ├── src/
│   │   ├── app/             # Next.js App Router Pages
│   │   │   ├── page.tsx          # Overview Page
│   │   │   ├── forecast/         # Forecast & Adaptive Blending Page
│   │   │   ├── live-globe/       # Interactive Live 3D Globe Page
│   │   │   ├── analytics/        # Scientific Verification Deck Page
│   │   │   ├── models/           # Models Registry Page
│   │   │   ├── extreme-events/   # Extreme Hazard Intelligence Page
│   │   │   ├── alerts/           # Alert Triggers & Rules Page
│   │   │   ├── data-sources/     # Provider Health & Latencies Page
│   │   │   ├── settings/         # Preferences & Cesium Token Page
│   │   │   ├── layout.tsx        # Liquid Glass Global Shell
│   │   │   └── globals.css       # Liquid Glass Tokens & Typography
│   │   ├── components/      # Sidebar, Header, Weather Widgets
│   │   └── lib/             # API Client
│   ├── public/              # SVG Logo, Portraits, Assets
│   ├── tailwind.config.ts   # Stitch Design Tokens (Colors, Radius, Spacing)
│   └── package.json
├── stitch_design/           # Extracted Stitch Project Artifacts (Project 7401513429137851547)
├── Dockerfile.backend       # Backend Docker Image
├── Dockerfile.frontend      # Frontend Docker Image
├── docker-compose.yml       # Production Multi-Container Orchestration
├── requirements.txt         # Backend Python Dependencies
├── .env.example             # Configuration Template
└── README.md
```

---

## 6. Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm 9+
- Docker & Docker Compose (Optional for containerized run)

### Setup & Local Execution

#### 1. Backend Setup
```bash
# Clone and enter workspace
cd AEROBLEND-AI

# Install Python dependencies
pip install torch --extra-index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

# Run ML Training Pipeline to generate gating network checkpoint
python backend/scripts/train_blender.py

# Run all backend tests (Unit, Invariants, API, Live Pipeline)
pytest backend/tests/ -v

# Start FastAPI backend
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```
Backend API will be available at: `http://localhost:8000` (Docs: `http://localhost:8000/docs`).

#### 2. Frontend Setup
```bash
# In a new terminal
cd frontend

# Install npm dependencies
npm install

# Run production build validation
npm run build

# Start Next.js development server
npm run dev
```
Frontend will be available at: `http://localhost:3000`.

---

## 7. Docker Compose Execution

To run the complete stack (TimescaleDB + FastAPI Backend + Next.js Frontend) in Docker:

```bash
docker compose up --build
```
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- PostgreSQL / TimescaleDB: `localhost:5432`

---

## 8. Verification & Baselines

AeroBlend AI benchmarks its blended predictions against:
- **Persistence** (Naïve zero-change baseline)
- **ECMWF IFS (0.1° HRES)**
- **ECMWF AIFS (0.25° Neural)**
- **NOAA GFS v16.3**
- **DWD ICON Global**
- **Simple Ensemble Mean**

Verification metrics strictly calculate:
$$\text{MAE} = \frac{1}{N} \sum_{i=1}^N |y_i - \hat{y}_i|$$
$$\text{RMSE} = \sqrt{\frac{1}{N} \sum_{i=1}^N (y_i - \hat{y}_i)^2}$$
$$\text{Bias} = \frac{1}{N} \sum_{i=1}^N (\hat{y}_i - y_i)$$
$$R^2 = \text{Corr}(y, \hat{y})^2$$

---

## 9. Failure Behavior & Scientific Integrity

1. **No Fake Data:** If external APIs are unreachable, AeroBlend AI surfaces an honest `DEGRADED` or `UNAVAILABLE` status with the last valid timestamp.
2. **Model Status Transparency:** The ML health check reports `TRAINED`, `TRAINING`, or `NOT_TRAINED`. If the model is not trained, fallback rule priors are clearly labeled.
3. **Cesium Fallback:** If `CESIUM_ION_TOKEN` is not supplied, the Live Globe gracefully falls back to an interactive atmospheric ellipsoid globe without crashing.
4. **Conservation of Weight:** The weight normalization module asserts $\sum w_i = 1.0$ at every timestep.

---

## 10. License & Credits

Built for the **Smart India Hackathon (SIH26081)**. Visual design created in **Google Stitch** (Project ID: `7401513429137851547`). Meteorological data courtesy of **Open-Meteo**, **ECMWF**, **NOAA/NCEP**, and **DWD**.
