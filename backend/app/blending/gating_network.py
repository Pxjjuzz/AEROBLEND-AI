from __future__ import annotations

import math
import os
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
import torch
import torch.nn as nn

from app.core.config import MODEL_KEYS, settings
from app.core.logging import get_logger
from app.features.spec import FEATURE_DIM, FEATURE_NAMES

logger = get_logger(__name__)

WeightBasis = str  # "gating_network" | "physical_prior"


@dataclass
class WeightResult:
    weights: Dict[str, float]
    available: List[str]
    basis: WeightBasis
    notes: List[str] = field(default_factory=list)

    @property
    def dominant(self) -> str:
        if not self.available:
            return "None"
        return max(self.available, key=lambda k: self.weights[k])


class AdaptiveGatingNetwork(nn.Module):
    """Maps a 19-dim atmospheric feature vector to a weight per model.

    Output order is the order of ``MODEL_REGISTRY`` in core.config.
    """

    def __init__(self, input_dim: int = FEATURE_DIM, num_models: int = len(MODEL_KEYS)):
        super().__init__()
        self.input_dim = input_dim
        self.num_models = num_models
        self.net = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.LayerNorm(64),
            nn.GELU(),
            nn.Linear(64, 32),
            nn.GELU(),
            nn.Linear(32, 16),
            nn.GELU(),
            nn.Linear(16, num_models),
        )
        self.softmax = nn.Softmax(dim=-1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.softmax(self.net(x))


def _seed_everything(seed: int = 42) -> None:
    """Seed torch and numpy.

    Without this the checkpoint written at Docker build time differed on every
    rebuild, so the deployed artefact was not reproducible.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def _largest_remainder_round(weights: Dict[str, float], keys: Sequence[str], places: int = 4) -> Dict[str, float]:
    """Round to a fixed number of places while preserving the exact sum.

    The previous implementation forced the entire residual onto whichever model
    happened to be last in the list (always DWD_ICON), biasing that model on
    100% of samples. Largest-remainder apportionment spreads the correction
    across all contributing models instead.
    """
    factor = 10 ** places
    exact = {k: weights[k] * factor for k in keys}
    floors = {k: math.floor(v) for k, v in exact.items()}
    shortfall = int(round(factor * sum(weights[k] for k in keys))) - sum(floors.values())
    remainders = sorted(keys, key=lambda k: exact[k] - floors[k], reverse=True)
    for i in range(max(0, shortfall)):
        floors[remainders[i % len(remainders)]] += 1
    return {k: round(floors[k] / factor, places) for k in keys}


class GatingModelManager:
    def __init__(self) -> None:
        self.model_path = str(settings.MODEL_WEIGHTS_PATH)
        self.device = torch.device(settings.ML_DEVICE)
        _seed_everything()
        self.model = AdaptiveGatingNetwork()
        self.model.to(self.device)
        self.model.eval()
        self.status = "NOT_TRAINED"
        self.model_names = list(MODEL_KEYS)
        self.notes: List[str] = []
        self._loaded_mtime: Optional[float] = None
        self.load_model()

    # -- Checkpoint ----------------------------------------------------------

    def load_model(self) -> bool:
        if not os.path.exists(self.model_path):
            self.status = "NOT_TRAINED"
            self.notes = ["no checkpoint found; using documented physical prior"]
            self._loaded_mtime = None
            return False
        try:
            # weights_only=True: the checkpoint is untrusted input. Without it
            # torch.load can execute arbitrary code.
            state_dict = torch.load(
                self.model_path, map_location=self.device, weights_only=True
            )
            self.model.load_state_dict(state_dict)
            self.model.eval()
            self.status = "TRAINED"
            self.notes = []
            self._loaded_mtime = os.path.getmtime(self.model_path)
            return True
        except Exception as exc:
            self.status = "ERROR"
            self.notes = [f"checkpoint load failed: {exc}"]
            self._loaded_mtime = None
            logger.error("gating network checkpoint load failed", extra={"context": {"error": str(exc)}})
            return False

    def reload_if_changed(self) -> None:
        """Reload only when the checkpoint mtime changed.

        The old code re-read the checkpoint on every single request.
        """
        try:
            mtime = os.path.getmtime(self.model_path)
        except OSError:
            if self.status == "TRAINED":
                self.status = "NOT_TRAINED"
                self.notes = ["checkpoint disappeared; using physical prior"]
            return
        if mtime != getattr(self, "_loaded_mtime", None):
            self.load_model()
            self._loaded_mtime = mtime

    # -- Weights -------------------------------------------------------------

    def _physical_prior(self, lead_time_hours: float) -> List[float]:
        """Documented climatological prior, used only when untrained.

        Ordered [ECMWF_IFS, ECMWF_AIFS, NOAA_GFS, DWD_ICON]. The neural model
        is favoured at short lead time; the longer-horizon NWP cores take over
        beyond 48 h.
        """
        if lead_time_hours <= 12:
            return [0.22, 0.48, 0.15, 0.15]
        if lead_time_hours <= 24:
            return [0.25, 0.40, 0.20, 0.15]
        if lead_time_hours <= 48:
            return [0.30, 0.30, 0.22, 0.18]
        return [0.32, 0.20, 0.28, 0.20]

    def _forward(self, feature_vector: np.ndarray) -> np.ndarray:
        with torch.no_grad():
            inp = torch.as_tensor(feature_vector, dtype=torch.float32, device=self.device)
            return self.model(inp.unsqueeze(0)).squeeze(0).cpu().numpy()

    def predict(
        self,
        feature_vector: np.ndarray,
        lead_time_hours: float = 24.0,
        available_models: Optional[Sequence[str]] = None,
    ) -> WeightResult:
        """Return weights summing to exactly 1.0 over the available models.

        ``available_models`` is the set of models that actually carry data for
        this step. Weights for unavailable models are masked to 0.0 and the
        remainder is redistributed proportionally across the available models.

        Masking is essential: Open-Meteo currently serves an all-null payload
        for ecmwf_aifs025, and the previous code silently retained its weight in
        the normalisation denominator, which biased every blended variable low
        by roughly that model's share.
        """
        available = [k for k in self.model_names if k in set(available_models or self.model_names)]
        notes: List[str] = []

        if not available:
            return WeightResult(
                weights={k: 0.0 for k in self.model_names}, available=[], basis="physical_prior",
                notes=["no model returned usable data"],
            )

        if self.status == "TRAINED":
            raw = self._forward(feature_vector)
            basis: WeightBasis = "gating_network"
        else:
            raw = np.array(self._physical_prior(lead_time_hours), dtype=np.float64)
            basis = "physical_prior"
            notes = list(self.notes)

        raw = np.nan_to_num(np.asarray(raw, dtype=np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        raw = np.clip(raw, 0.0, None)

        indices = {k: self.model_names.index(k) for k in available}
        masked = np.array([raw[indices[k]] for k in available], dtype=np.float64)
        total = masked.sum()

        if total <= 0.0:
            # Degenerate network output: fall back to an equal split so the
            # sum invariant still holds rather than dividing by zero.
            masked = np.ones(len(available), dtype=np.float64)
            total = masked.sum()
            notes.append("degenerate gating output; used equal weights")

        masked = masked / total
        renormalised = _largest_remainder_round(
            {k: float(m) for k, m in zip(available, masked)}, available
        )

        weights = {k: 0.0 for k in self.model_names}
        weights.update(renormalised)
        return WeightResult(weights=weights, available=available, basis=basis, notes=notes)

    def predict_weights(
        self,
        feature_vector: np.ndarray,
        lead_time_hours: float = 24.0,
        available_models: Optional[Sequence[str]] = None,
    ) -> Dict[str, float]:
        """Backwards-compatible convenience wrapper returning the weight dict."""
        return self.predict(
            feature_vector, lead_time_hours, available_models
        ).weights

    # -- Explainability ------------------------------------------------------

    def sensitivity(
        self, feature_vector: np.ndarray, lead_time_hours: float = 24.0
    ) -> List[Dict[str, float]]:
        """Measured per-feature influence on the weight vector.

        Each feature is perturbed by +/- one standard deviation of its observed
        cross-model spread (or a documented default when the input is constant)
        and the resulting change in the total-variation distance of the weight
        vector is recorded. These are measured sensitivities, not asserted
        scores, and they work for the physical prior as well as a trained net.
        """
        base = self.predict(feature_vector, lead_time_hours).weights
        base_vec = np.array([base[k] for k in self.model_names])
        out: List[Dict[str, float]] = []

        for idx, name in enumerate(FEATURE_NAMES):
            feature_vector = np.asarray(feature_vector, dtype=np.float32)
            if name.startswith("hour_") or name.startswith("month_"):
                step = 0.35
            elif name.startswith("regime_"):
                step = 1.0
            else:
                step = 0.25

            deltas = []
            for sign in (1.0, -1.0):
                probe = feature_vector.copy()
                probe[idx] = float(np.clip(probe[idx] + sign * step, -10.0, 10.0))
                weights = self.predict(probe, lead_time_hours).weights
                vec = np.array([weights[k] for k in self.model_names])
                deltas.append(0.5 * float(np.abs(vec - base_vec).sum()))
            out.append(
                {
                    "feature": name,
                    "index": float(idx),
                    "sensitivity": float(max(deltas)),
                    "perturbation": step,
                }
            )
        out.sort(key=lambda d: d["sensitivity"], reverse=True)
        return out


gating_manager = GatingModelManager()

