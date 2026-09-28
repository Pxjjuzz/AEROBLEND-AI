from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from app.blending.gating_network import gating_manager
from app.core.logging import get_logger
from app.features.spec import FEATURE_NAMES
from app.schemas.weather import (
    ExplainabilityAttribution,
    ExplainabilityReport,
    ModelDisagreement,
    WeightDistribution,
    WeatherRegime,
)

logger = get_logger(__name__)

# Human-readable category and interpretation for each measured feature.
FEATURE_MEANING: Dict[str, tuple[str, str]] = {
    "lat": ("Spatial", "Latitude sets the large-scale circulation regime"),
    "lon": ("Spatial", "Longitude selects the upstream moisture source and orography"),
    "elevation": ("Spatial", "Terrain height controls lapse rate and orographic forcing"),
    "hour_sin": ("Diurnal", "Time of day (sine component) shifts the diurnal heating cycle"),
    "hour_cos": ("Diurnal", "Time of day (cosine component) shifts the diurnal heating cycle"),
    "month_sin": ("Seasonal", "Calendar month (sine component) sets the solar declination"),
    "month_cos": ("Seasonal", "Calendar month (cosine component) sets the solar declination"),
    "lead_time_hours": ("Temporal Horizon", "Forecast horizon: neural skill decays faster than NWP skill"),
    "temp_mean": ("Thermodynamics", "Ensemble mean temperature"),
    "humidity_mean": ("Thermodynamics", "Ensemble mean relative humidity"),
    "pressure_mean": ("Thermodynamics", "Ensemble mean surface pressure"),
    "wind_speed_mean": ("Thermodynamics", "Ensemble mean wind speed"),
    "precip_mean": ("Precipitation", "Ensemble mean precipitation"),
    "precip_std": ("Model Agreement", "Inter-model precipitation dispersion"),
    "temp_std": ("Model Agreement", "Inter-model temperature dispersion"),
    "dew_point_depression": ("Thermodynamics", "Dew point depression, a low-level moisture proxy"),
    "regime_convective": ("Synoptic Regime", "Convective regime indicator"),
    "regime_monsoon": ("Synoptic Regime", "Monsoon regime indicator"),
    "regime_extreme": ("Synoptic Regime", "Extreme regime indicator"),
}

DIRECTION_BY_SIGN = {
    "precip_std": ("HIGHER_SPREAD", "NARROWER_SPREAD"),
    "temp_std": ("HIGHER_SPREAD", "NARROWER_SPREAD"),
    "precip_mean": ("WETTER_INPUT", "DRIER_INPUT"),
    "regime_monsoon": ("ACTIVATED", "DEACTIVATED"),
    "regime_convective": ("ACTIVATED", "DEACTIVATED"),
    "regime_extreme": ("ACTIVATED", "DEACTIVATED"),
}


class ExplainabilityEngine:
    """Attribution computed from measured gating-network sensitivities.

    The previous implementation returned a fixed impact score per category
    (38.5 / 42.0 / 25.0 / 88.0 / 65.0) and a fixed coherence index
    (94.8 / 88.5 / 76.2) that were not derived from the forecast at all. This
    version perturbs each input feature and records the actual change in the
    weight vector, so every reported number is traceable to the model.
    """

    def explain(
        self,
        *,
        weights: WeightDistribution,
        regime: WeatherRegime,
        disagreement: ModelDisagreement,
        feature_vector: Optional[np.ndarray] = None,
        lead_time_hours: Optional[int] = None,
    ) -> ExplainabilityReport:
        lead = lead_time_hours if lead_time_hours is not None else weights.leadTimeHours
        dominant = weights.dominantModel
        dom_weight = next(
            (w.weight for w in weights.weights if w.modelName == dominant), 0.0
        )

        attributions: List[ExplainabilityAttribution] = []

        # A perturbation of the physical prior genuinely produces zero change,
        # because that prior is a function of lead time alone. Reporting those
        # as measured features with an "INCREASED_WEIGHT" direction would be
        # fabricated attribution, so the untrained case is stated instead.
        prior_only = weights.basis != "gating_network"

        if feature_vector is not None:
            try:
                sensitivities = gating_manager.sensitivity(feature_vector, float(lead))
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "sensitivity analysis failed", extra={"context": {"error": str(exc)}}
                )
                sensitivities = []
            top = sensitivities[:5] if not prior_only else []
        else:
            top = []

        for entry in top:
            name = entry["feature"]
            category, meaning = FEATURE_MEANING.get(name, ("Other", "Unclassified driver"))
            up, down = DIRECTION_BY_SIGN.get(
                name, ("INCREASED_WEIGHT", "REDUCED_WEIGHT")
            )
            attributions.append(
                ExplainabilityAttribution(
                    featureName=name,
                    category=category,
                    # Total-variation distance in weight space, scaled to 0-100.
                    impactScore=round(min(100.0, entry["sensitivity"] * 100.0), 2),
                    direction=up,
                    observedValue=round(float(feature_vector[int(entry["index"])]), 4)
                    if feature_vector is not None
                    else None,
                    rationale=(
                        f"Perturbing {name.replace('_', ' ')} by "
                        f"+/-{entry['perturbation']:.2f} in normalised units shifted the "
                        f"weight vector by {entry['sensitivity'] * 100:.2f} total-variation "
                        f"points. {meaning}."
                    ),
                )
            )

        if not attributions:
            if prior_only:
                attributions.append(
                    ExplainabilityAttribution(
                        featureName="lead_time_hours",
                        category="Temporal Horizon",
                        impactScore=100.0,
                        direction="SHORTENED_LEAD",
                        observedValue=float(lead),
                        rationale=(
                            "Weights currently come from the documented physical prior, "
                            "which is a step function of forecast lead time and does not "
                            "depend on the atmospheric state. Lead time is therefore the "
                            "only real driver. Per-feature attribution requires a trained "
                            "gating checkpoint."
                        ),
                    )
                )
            else:
                attributions.append(
                    ExplainabilityAttribution(
                        featureName="unavailable",
                        category="Other",
                        impactScore=0.0,
                        direction="NEUTRAL",
                        observedValue=None,
                        rationale=(
                            "Feature vector was not supplied, so no measured attribution "
                            "could be produced."
                        ),
                    )
                )

        coherence, coherence_note = self._coherence(disagreement, weights)

        summary = (
            f"{dominant} received the largest weight ({dom_weight * 100:.1f}%) at "
            f"T+{lead} h under the {regime.regime} regime. Member agreement is "
            f"{disagreement.spreadLevel} across {disagreement.sampleCount} models "
            f"(sigma {disagreement.stdDev:.2f} mm, range {disagreement.range:.1f} mm)."
        )

        dominant_rationale = (
            f"Under the {regime.regime} regime the gating network allocated "
            f"{dom_weight * 100:.1f}% to {dominant}. Contributing models at this step: "
            f"{', '.join(weights.availableModels) or 'none'}. This is the measured "
            "output of the network for the current atmospheric state, not a "
            "predefined ranking."
        )
        if prior_only:
            dominant_rationale = (
                f"{dominant} holds the largest share of the documented physical prior "
                f"({dom_weight * 100:.1f}%) for a T+{lead} h horizon under the "
                f"{regime.regime} regime. Contributing models: "
                f"{', '.join(weights.availableModels) or 'none'}. No trained checkpoint "
                "is loaded, so these weights reflect climatological model skill, not a "
                "response to the current atmospheric state."
            )

        return ExplainabilityReport(
            summary=summary,
            coherenceIndex=coherence,
            attributions=attributions,
            dominantModelRationale=dominant_rationale,
            method=(
                "input perturbation of the gating network, measured as total-variation "
                "distance between weight vectors"
                if not prior_only
                else (
                    "not applicable: weights come from the physical prior, which depends "
                    "only on forecast lead time"
                )
            ),
            basedOnTrainedModel=weights.basis == "gating_network",
        )

    @staticmethod
    def _coherence(
        disagreement: ModelDisagreement, weights: WeightDistribution
    ) -> tuple[float, str]:
        """Coherence derived from measured spread and member count."""
        n = max(1, disagreement.sampleCount)
        spread = disagreement.stdDev
        scale = max(spread, 1e-6)
        spread_penalty = min(50.0, spread * 6.0)
        count_bonus = min(15.0, n * 5.0)
        value = 100.0 - spread_penalty + count_bonus
        value = round(max(0.0, min(100.0, value)), 1)
        return value, f"100 - min(50, sigma*6) + min(15, n*5) = {value}"


explainability_engine = ExplainabilityEngine()

