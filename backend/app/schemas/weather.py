from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

DataQuality = Literal["OK", "DEGRADED", "UNAVAILABLE"]


class ForecastPoint(BaseModel):
    timestamp: str
    validTime: Optional[str] = None
    latitude: float
    longitude: float
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    dewPoint: Optional[float] = None
    pressure: Optional[float] = None
    windSpeed: Optional[float] = None
    windDirection: Optional[float] = None
    windU: Optional[float] = None
    windV: Optional[float] = None
    precipitation: Optional[float] = None
    cloudCover: Optional[float] = None
    weatherCode: Optional[int] = None
    modelName: str
    provider: str
    modelRun: str
    leadTimeHours: int


class LocationInfo(BaseModel):
    name: str
    latitude: float
    longitude: float
    elevation: Optional[float] = 0.0
    country: Optional[str] = "India"
    admin1: Optional[str] = None
    timezone: Optional[str] = "UTC"
    elevationSource: Optional[str] = None


class ModelWeight(BaseModel):
    modelName: str
    weight: float
    forecastValue: Optional[float] = None
    differenceFromBlend: Optional[float] = None
    available: bool = True


class WeightDistribution(BaseModel):
    variable: str
    leadTimeHours: int
    weights: List[ModelWeight]
    sumWeights: float
    dominantModel: str
    # Weights are renormalised over contributing models only; this records
    # which models actually carried data for the step being displayed.
    availableModels: List[str] = Field(default_factory=list)
    basis: Literal["gating_network", "physical_prior"] = "gating_network"


class WeatherRegime(BaseModel):
    regime: str  # NORMAL, MONSOON, CONVECTIVE, EXTREME
    confidence: float
    synopticCluster: str
    convectiveIndex: float
    orographicIndex: float
    description: str
    # Observed inputs, so a caller can audit how the label was reached.
    observed: Dict[str, float] = Field(default_factory=dict)


class ModelDisagreement(BaseModel):
    variable: str
    mean: float
    min: float
    max: float
    range: float
    stdDev: float
    spreadLevel: str  # LOW, MODERATE, HIGH, INSUFFICIENT_MODELS
    description: str
    sampleCount: int = 0
    # The statistic the level was derived from, so the label and the printed
    # number can never refer to different quantities.
    thresholdBasis: str = "stdDev"


class ExtremeEvent(BaseModel):
    id: str
    eventType: str  # HEAVY_RAINFALL, HEAT_WAVE, HIGH_WIND, CONVECTIVE_BURST
    severity: str  # ADVISORY, MODERATE, HIGH, SEVERE
    time: str
    leadTimeHours: int
    durationHours: int
    intensityValue: float
    unit: str
    location: str
    modelAgreement: float
    details: str
    # Measured, not asserted: 1 - normalised inter-model spread for the
    # timestep that produced the event.
    modelAgreementBasis: Optional[str] = None


class ExplainabilityAttribution(BaseModel):
    featureName: str
    category: str
    impactScore: float
    direction: str
    observedValue: Optional[float] = None
    rationale: str


class ExplainabilityReport(BaseModel):
    summary: str
    coherenceIndex: float
    attributions: List[ExplainabilityAttribution]
    dominantModelRationale: str
    method: str
    # True when the underlying gating network is a trained checkpoint; False
    # when weights come from the documented physical prior.
    basedOnTrainedModel: bool = True


class BlendedForecastPoint(BaseModel):
    timestamp: str
    validTime: Optional[str] = None
    leadTimeHours: int
    temperature: float
    humidity: float
    dewPoint: Optional[float] = None
    pressure: float
    windSpeed: float
    windDirection: float
    precipitation: float
    pop: Optional[float] = None
    weatherCode: int
    conditionText: str
    dominantSource: str
    confidencePercentage: Optional[float] = None
    confidenceIntervalLow: Optional[float] = None
    confidenceIntervalHigh: Optional[float] = None
    # Explicitly states what the interval represents. A spread across models is
    # an ensemble envelope, not a calibrated 90% interval; the previous code
    # presented it as the latter without ever measuring forecast error.
    uncertaintyBasis: Optional[str] = None
    # Models that contributed to this timestep after masking.
    contributingModels: List[str] = Field(default_factory=list)


class BlendedForecastResponse(BaseModel):
    location: LocationInfo
    generatedAt: str
    status: str
    dataQuality: DataQuality = "OK"
    statusDetail: Optional[str] = None
    availableModels: List[str] = Field(default_factory=list)
    unavailableModels: List[str] = Field(default_factory=list)
    gatingNetworkStatus: str = "NOT_TRAINED"
    weightBasis: Literal["gating_network", "physical_prior"] = "gating_network"
    activeRegime: WeatherRegime
    disagreement: ModelDisagreement
    weights: WeightDistribution
    # Optional by contract: a provider outage must yield an honest partial
    # response, not a 500 from Pydantic validation.
    currentBlend: Optional[BlendedForecastPoint] = None
    hourlyTrajectory: List[BlendedForecastPoint] = Field(default_factory=list)
    modelForecasts: Dict[str, List[ForecastPoint]] = Field(default_factory=dict)
    extremeEvents: List[ExtremeEvent] = Field(default_factory=list)
    explainability: ExplainabilityReport


class HistoricalAnalogueMatch(BaseModel):
    date: str
    location: str
    similarityPercentage: float
    synopticMatchName: str
    description: str
    matchedState: Dict[str, float] = Field(default_factory=dict)
    # Observed outcome in the 24h following the matched state.
    outcome24h: Dict[str, float] = Field(default_factory=dict)
    distance: Optional[float] = None


class AnalogueSearchResult(BaseModel):
    queryCoordinates: Dict[str, float]
    searchDatabase: str
    vectorSimilarityMethod: str
    searchWindow: Dict[str, Any] = Field(default_factory=dict)
    sampleCount: int = 0
    matches: List[HistoricalAnalogueMatch] = Field(default_factory=list)


class VerificationMetric(BaseModel):
    modelName: str
    variable: str
    leadTimeHours: int
    mae: float
    rmse: float
    bias: float
    correlationR2: Optional[float] = None
    sampleCount: int
    evaluationPeriod: str


class LeadTimeBin(BaseModel):
    leadTime: int
    sampleCount: int
    metrics: Dict[str, float] = Field(default_factory=dict)


class VerificationReport(BaseModel):
    location: str
    referenceDataset: str
    referenceNote: str
    variable: str
    leadTimeHours: int
    evaluationPeriod: str
    periodStart: str
    periodEnd: str
    sampleCount: int
    overallMae: float
    overallRmse: float
    skillScoreVsPersistence: float
    falseAlarmRatio: float
    modelComparisons: List[VerificationMetric] = Field(default_factory=list)
    leadTimeDegradation: List[LeadTimeBin] = Field(default_factory=list)
    regionalMatrix: List[Dict[str, Any]] = Field(default_factory=list)
    computed: bool = True
    # Why a report has computed=False. Previously the reason was accepted by
    # the builder and then dropped, so a failed verification was
    # indistinguishable from a perfect one apart from a bare false flag.
    unavailableReason: Optional[str] = None


class ProviderHealth(BaseModel):
    provider: str
    model: str
    displayName: Optional[str] = None
    status: str  # OPERATIONAL, DEGRADED, UNAVAILABLE
    latencyMs: float
    lastSuccessfulRun: Optional[str] = None
    lastChecked: Optional[str] = None
    updateFrequency: str
    coverage: str
    resolution: str
    error: Optional[str] = None


class ModelRunInfo(BaseModel):
    model: str
    displayName: Optional[str] = None
    cycle: Optional[str] = None
    status: str
    leadHorizonHours: Optional[int] = None
    available: bool = True
