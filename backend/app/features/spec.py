"""Canonical definition of the 19-dimensional gating network input vector.

Previously this list was duplicated by hand in ``features/engineer.py`` and
``scripts/train_blender.py``. Any drift between the two was invisible at
runtime because the network's first ``LayerNorm`` normalises away scale, so a
mismatched feature would silently degrade blending quality instead of raising.
Both the runtime extractor and the training pipeline now import from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

FEATURE_NAMES: List[str] = [
    "lat",
    "lon",
    "elevation",
    "hour_sin",
    "hour_cos",
    "month_sin",
    "month_cos",
    "lead_time_hours",
    "temp_mean",
    "humidity_mean",
    "pressure_mean",
    "wind_speed_mean",
    "precip_mean",
    "precip_std",
    "temp_std",
    "dew_point_depression",
    "regime_convective",
    "regime_monsoon",
    "regime_extreme",
]

FEATURE_DIM = len(FEATURE_NAMES)

assert FEATURE_DIM == 19, "gating network input dimension is fixed at 19"


@dataclass(frozen=True)
class FeatureScale:
    """Divisor and offset for each feature, so train and serve agree exactly.

    ``value / divisor`` for unbounded features, ``(value - offset) / divisor``
    otherwise.
    """

    divisor: float
    offset: float = 0.0


SCALES = {
    "lat": FeatureScale(90.0),
    "lon": FeatureScale(180.0),
    "elevation": FeatureScale(4000.0),
    "hour_sin": FeatureScale(1.0),
    "hour_cos": FeatureScale(1.0),
    "month_sin": FeatureScale(1.0),
    "month_cos": FeatureScale(1.0),
    "lead_time_hours": FeatureScale(120.0),
    "temp_mean": FeatureScale(30.0, 20.0),
    "humidity_mean": FeatureScale(100.0),
    "pressure_mean": FeatureScale(50.0, 1013.25),
    "wind_speed_mean": FeatureScale(50.0),
    "precip_mean": FeatureScale(50.0),
    "precip_std": FeatureScale(20.0),
    "temp_std": FeatureScale(10.0),
    "dew_point_depression": FeatureScale(20.0),
    "regime_convective": FeatureScale(1.0),
    "regime_monsoon": FeatureScale(1.0),
    "regime_extreme": FeatureScale(1.0),
}

# Clamp used before scaling, matching the original implementation.
CLAMPS = {
    "elevation": (None, 4000.0),
    "lead_time_hours": (None, 120.0),
    "precip_mean": (None, 50.0),
    "precip_std": (None, 20.0),
    "temp_std": (None, 10.0),
    "dew_point_depression": (None, 20.0),
}

REGIME_FLAGS = {
    "CONVECTIVE": "regime_convective",
    "MONSOON": "regime_monsoon",
    "EXTREME": "regime_extreme",
}


def scale(name: str, value: float) -> float:
    """Apply the canonical clamp + scale for one feature."""
    lo, hi = CLAMPS.get(name, (None, None))
    if hi is not None:
        value = min(float(value), hi)
    if lo is not None:
        value = max(float(value), lo)
    spec = SCALES[name]
    return float(np.clip((value - spec.offset) / spec.divisor, -10.0, 10.0))


def build_vector(raw: dict) -> np.ndarray:
    """Assemble the feature vector from a raw (unnormalised) value mapping."""
    missing = [name for name in FEATURE_NAMES if name not in raw]
    if missing:
        raise KeyError(f"missing raw features: {missing}")
    return np.array([scale(name, raw[name]) for name in FEATURE_NAMES], dtype=np.float32)

