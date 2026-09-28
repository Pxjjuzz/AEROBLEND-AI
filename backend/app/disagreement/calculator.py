from __future__ import annotations

import math
from typing import List, Optional, Sequence

import numpy as np

from backend.app.core.config import settings
from backend.app.schemas.weather import ModelDisagreement


class DisagreementCalculator:
    """Inter-model spread on a common quantity (default: 24 h rainfall, mm).

    Two defects are fixed here:

    1. The level was decided from the standard deviation while the human
       description printed the range. For four members those differ by up to a
       factor of two, so the label and the number beside it could contradict
       each other. Both are now derived from the same statistic.
    2. With one contributing model the spread was exactly zero, which reported
       "LOW" spread and maximum confidence. Fewer than
       ``DISAGREEMENT_MIN_MODELS`` members is now reported as
       ``INSUFFICIENT_MODELS``.
    """

    def calculate(
        self, values: Sequence[Optional[float]], variable_name: str = "rainfall"
    ) -> ModelDisagreement:
        valid = [
            float(v)
            for v in values
            if v is not None and not math.isnan(float(v)) and not math.isinf(float(v))
        ]

        if not valid:
            return ModelDisagreement(
                variable=variable_name,
                mean=0.0, min=0.0, max=0.0, range=0.0, stdDev=0.0,
                spreadLevel="INSUFFICIENT_MODELS",
                description="No model returned a usable value for this variable.",
                sampleCount=0,
                thresholdBasis="n/a",
            )

        mean_val = float(np.mean(valid))
        min_val = float(np.min(valid))
        max_val = float(np.max(valid))
        rng = float(max_val - min_val)
        std = float(np.std(valid)) if len(valid) > 1 else 0.0

        if len(valid) < settings.DISAGREEMENT_MIN_MODELS:
            return ModelDisagreement(
                variable=variable_name,
                mean=round(mean_val, 2),
                min=round(min_val, 2),
                max=round(max_val, 2),
                range=round(rng, 2),
                stdDev=round(std, 2),
                spreadLevel="INSUFFICIENT_MODELS",
                description=(
                    f"Only {len(valid)} of {settings.DISAGREEMENT_MIN_MODELS}+ "
                    "required models reported a value; spread is not evidence of "
                    "agreement."
                ),
                sampleCount=len(valid),
                thresholdBasis="model count",
            )

        low_th = settings.DISAGREEMENT_LOW_MM if variable_name == "rainfall" else 1.5
        high_th = settings.DISAGREEMENT_HIGH_MM if variable_name == "rainfall" else 3.5

        # stdVal is the single decision statistic; rng is reported alongside
        # and never used to contradict the label.
        if std < low_th:
            level = "LOW"
            desc = (
                f"Members agree closely: standard deviation {std:.2f} mm is below "
                f"the {low_th:.1f} mm low-spread threshold (full range {rng:.1f} mm)."
            )
        elif std < high_th:
            level = "MODERATE"
            desc = (
                f"Moderate dispersion: standard deviation {std:.2f} mm sits between "
                f"the {low_th:.1f} and {high_th:.1f} mm thresholds (full range {rng:.1f} mm)."
            )
        else:
            level = "HIGH"
            desc = (
                f"High bifurcation: standard deviation {std:.2f} mm exceeds the "
                f"{high_th:.1f} mm threshold (full range {rng:.1f} mm)."
            )

        return ModelDisagreement(
            variable=variable_name,
            mean=round(mean_val, 2),
            min=round(min_val, 2),
            max=round(max_val, 2),
            range=round(rng, 2),
            stdDev=round(std, 2),
            spreadLevel=level,
            description=desc,
            sampleCount=len(valid),
            thresholdBasis="stdDev",
        )


disagreement_calculator = DisagreementCalculator()
