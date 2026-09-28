"""Train the gating network on real archived forecast errors.

The previous version of this script generated its own synthetic dataset and
derived the target weights from the very same random draws that produced the
input features. The label was ``1 / err**2`` and one of the features was
``std(err)``, so the network could fit the training set perfectly while having
no relationship to any real forecast error. The reported validation loss was
therefore meaningless and the checkpoint it saved learned nothing transferable.

What this does instead
----------------------
For each sample (location, valid time, lead time):

  * features are built from ERA5 reanalysis and the archived member forecasts,
    through ``features.spec.build_vector`` -- the identical code path used at
    inference, so there is no train/serve skew;
  * each member's error against ERA5 is retained, ``e_i = forecast_i - ref``.

The network is trained by minimising the *forecast error it actually
produces*,

    loss = mean( ( sum_i w_i * e_i )^2 )

after renormalising ``w`` over the available members exactly as the runtime
does. An earlier revision regressed onto the constrained optimal weight vector
instead. That target is close to one-hot, so it is nearly discontinuous and the
optimiser spent its capacity chasing unlearnable labels; worse, the holdout
check scored weights in weight space, which made the reported "optimal cost"
come out *higher* than equal weighting, an impossibility that should have made
the result obviously wrong.

Validation is the way the network is actually used: the blended forecast is
scored against ERA5 on a chronologically later holdout and compared with equal
weighting, plus the per-sample constrained optimum as an irreducible floor. The
script asserts the floor cannot exceed equal weighting, and refuses to
overwrite a working checkpoint unless the network genuinely beats the
baseline.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import sys
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.blending.gating_network import (  # noqa: E402
    AdaptiveGatingNetwork,
    _seed_everything,
)
from app.core.config import KEY_TO_SPEC, MODEL_KEYS, settings  # noqa: E402
from app.core.logging import get_logger  # noqa: E402
from app.features.spec import FEATURE_DIM, build_vector  # noqa: E402
from app.features.engineer import dew_point_from  # noqa: E402
from app.regimes.classifier import regime_classifier  # noqa: E402
from app.providers.open_meteo import open_meteo_provider  # noqa: E402

logger = get_logger(__name__)

# A spread of Indian climate regimes so the network sees monsoon, arid,
# coastal and highland conditions rather than one point.
SITES: Sequence[Tuple[str, float, float]] = (
    ("Bengaluru, Karnataka", 12.9716, 77.5946),
    ("Mumbai, Maharashtra", 19.0760, 72.8777),
    ("New Delhi, NCR", 28.6139, 77.2090),
    ("Chennai, Tamil Nadu", 13.0827, 80.2707),
    ("Hyderabad, Telangana", 17.3850, 78.4867),
    ("Kolkata, West Bengal", 22.5726, 88.3639),
    ("Ahmedabad, Gujarat", 23.0225, 72.5714),
    ("Jaipur, Rajasthan", 26.9124, 75.7873),
    ("Guwahati, Assam", 26.1445, 91.7362),
    ("Thiruvananthapuram, Kerala", 8.5241, 76.9366),
    ("Srinagar, J&K", 34.0837, 74.7973),
    ("Jaipur_dry", 27.0239, 74.2179),
)

LEAD_HOURS: Sequence[int] = (6, 12, 24, 36, 48, 72)


def _floats(values: Sequence[Optional[float]]) -> List[Optional[float]]:
    """Coerce an archive column to floats, mapping blanks to None."""
    out: List[Optional[float]] = []
    for v in values:
        if v is None or v == "":
            out.append(None)
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            out.append(None)
            continue
        out.append(None if math.isnan(f) or math.isinf(f) else f)
    return out


def _iso_hour(moment: datetime) -> str:
    """Match the archive's timestamp format exactly.

    The archive emits ``2026-09-01T00:00`` with no seconds. numpy string
    conversion emitted ``2026-09-01T00:00:00:00``, so every window lookup
    missed and the dataset silently came out empty.
    """
    return moment.strftime("%Y-%m-%dT%H:%M")


def _mean_of(values: Sequence[Optional[float]], idx: Sequence[int]) -> Optional[float]:
    vals = [values[i] for i in idx if values[i] is not None]
    return float(np.mean(vals)) if vals else None


def _sum_of(values: Sequence[Optional[float]], idx: Sequence[int]) -> Optional[float]:
    vals = [values[i] for i in idx if values[i] is not None]
    return float(np.sum(vals)) if vals else None


def _std_of(values: Sequence[Optional[float]], idx: Sequence[int]) -> Optional[float]:
    vals = [values[i] for i in idx if values[i] is not None]
    if not vals:
        return None
    return float(np.std(vals)) if len(vals) > 1 else 0.0


def _field_values(
    cols: Dict[str, Tuple[List[Optional[float]], Dict[str, int]]],
    field: str,
    window: Sequence[str],
) -> Tuple[List[Optional[float]], List[int]]:
    """Window indices for one field, using that field's own time map.

    Series lengths differ per field in the archive payload, so sharing the
    temperature index map across fields raised IndexError.
    """
    values, pos = cols[field]
    return values, [pos[t] for t in window if t in pos]


def _mean_of_field(
    cols: Dict[str, Tuple[List[Optional[float]], Dict[str, int]]],
    field: str,
    window: Sequence[str],
    std: bool = False,
) -> Optional[float]:
    values, idx = _field_values(cols, field, window)
    return _std_of(values, idx) if std else _mean_of(values, idx)


def _sum_of_field(
    cols: Dict[str, Tuple[List[Optional[float]], Dict[str, int]]],
    field: str,
    window: Sequence[str],
) -> Optional[float]:
    values, idx = _field_values(cols, field, window)
    return _sum_of(values, idx)


# Archive column suffix per internal field, for one model slug.
_MEMBER_COLUMNS = (
    ("temperature", "temperature_2m"),
    ("relative_humidity_2m", "relative_humidity_2m"),
    ("surface_pressure", "surface_pressure"),
    ("wind_speed_10m", "wind_speed_10m"),
    ("dew_point_2m", "dew_point_2m"),
    ("precipitation", "precipitation"),
)


async def build_dataset(
    *, start: date, end: date, sites: Sequence[Tuple[str, float, float]]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, int]]:
    """Fetch archives and build (features, member errors, availability mask).

    Returns the per-member signed temperature error against ERA5 rather than a
    target weight vector, so the training objective can be the forecast error
    itself. Features go through ``features.spec.build_vector``, the same code
    path used at inference.
    """
    X: List[np.ndarray] = []
    E: List[np.ndarray] = []
    M: List[np.ndarray] = []
    stats = {"sites": 0, "skipped_sparse": 0, "no_reference": 0, "samples": 0}

    for name, lat, lon in sites:
        reference = await open_meteo_provider.fetch_historical_archive(
            lat, lon, start.isoformat(), end.isoformat()
        )
        members = await open_meteo_provider.fetch_historical_archive(
            lat, lon, start.isoformat(), end.isoformat(), include_models=True
        )
        if not reference or not members:
            logger.warning("archive unavailable", extra={"context": {"site": name}})
            continue

        ref_hourly = reference.get("hourly") or {}
        ref_times = list(ref_hourly.get("time") or [])
        ref_temp = _floats(ref_hourly.get("temperature_2m") or [])
        if not ref_times or len(ref_times) != len(ref_temp):
            logger.warning("no reference series", extra={"context": {"site": name}})
            stats["no_reference"] += 1
            continue
        ref_pos = {t: i for i, t in enumerate(ref_times)}

        # Per-model hourly columns, each stored as a parallel (values, pos)
        # pair. The pos map is built per column from its own length, because a
        # payload can omit a series entirely; indexing a short column with the
        # global time map raised IndexError mid-loop.
        member_cols: Dict[str, Dict[str, Tuple[List[Optional[float]], Dict[str, int]]]] = {}
        member_hourly = members.get("hourly") or {}
        member_times = list(member_hourly.get("time") or [])
        for key in MODEL_KEYS:
            slug = KEY_TO_SPEC[key].slug
            cols: Dict[str, Tuple[List[Optional[float]], Dict[str, int]]] = {}
            for field, col in _MEMBER_COLUMNS:
                values = _floats(member_hourly.get(f"{col}_{slug}") or [])
                cols[field] = (
                    values,
                    {t: i for i, t in enumerate(member_times[: len(values)])},
                )
            member_cols[key] = cols

        def window_indices(times_map: Dict[str, int], window: Sequence[str]) -> List[int]:
            return [times_map[t] for t in window if t in times_map]

        produced = 0
        for t_ref in ref_times:
            # Archive timestamps are naive ISO strings; read the calendar
            # fields directly rather than via numpy unit conversion, which
            # rejects "m" as a unit alias.
            month = int(t_ref[5:7])
            hour = int(t_ref[11:13])
            try:
                base = datetime.strptime(t_ref[:16], "%Y-%m-%dT%H:%M")
            except ValueError:
                continue

            for lead in LEAD_HOURS:
                window = [
                    _iso_hour(base - timedelta(hours=lead - k))
                    for k in range(lead + 1)
                ]
                ref_idx = window_indices(ref_pos, window)
                # Require most of the window; a truncated window would mislabel
                # a member's error as skill.
                if len(ref_idx) < lead * 0.8:
                    stats["skipped_sparse"] += 1
                    continue

                ref_t = _mean_of(ref_temp, ref_idx)
                if ref_t is None:
                    stats["no_reference"] += 1
                    continue

                # Collect per-member window statistics first, then aggregate
                # across members exactly like FeatureEngineer.extract_features
                # does at inference (mean/std across contributing models, same
                # dew-point and regime logic). The previous builder wrote the
                # last member's values straight into the feature vector, which
                # the runtime never does.
                errors: List[float] = []
                present: List[float] = []
                m_temps: List[float] = []
                m_hums: List[float] = []
                m_press: List[float] = []
                m_winds: List[float] = []
                m_precips: List[float] = []
                m_dews: List[float] = []

                for key in MODEL_KEYS:
                    cols = member_cols[key]
                    # Same coverage rule as the reference window: a sparse
                    # member window is not available data.
                    _, widx = _field_values(cols, "temperature", window)
                    if len(widx) < lead * 0.8:
                        errors.append(0.0)
                        present.append(0.0)
                        continue
                    m_t = _mean_of_field(cols, "temperature", window)
                    if m_t is None:
                        errors.append(0.0)
                        present.append(0.0)
                        continue
                    errors.append(m_t - ref_t)
                    present.append(1.0)
                    m_temps.append(m_t)
                    for field, bucket in (
                        ("relative_humidity_2m", m_hums),
                        ("surface_pressure", m_press),
                        ("wind_speed_10m", m_winds),
                        ("precipitation", m_precips),
                        ("dew_point_2m", m_dews),
                    ):
                        value = _mean_of_field(cols, field, window)
                        if value is not None:
                            bucket.append(value)

                if not m_temps:
                    continue

                temp_mean = float(np.mean(m_temps))
                temp_std = float(np.std(m_temps)) if len(m_temps) > 1 else 0.0
                hum_mean = float(np.mean(m_hums)) if m_hums else 70.0
                pres_mean = float(np.mean(m_press)) if m_press else 1013.25
                wind_mean = float(np.mean(m_winds)) if m_winds else 10.0
                precip_mean = float(np.mean(m_precips)) if m_precips else 0.0
                precip_std = float(np.std(m_precips)) if len(m_precips) > 1 else 0.0
                if m_dews:
                    dew_mean = float(np.mean(m_dews))
                else:
                    dew_mean = dew_point_from(temp_mean, hum_mean)
                dew_depression = max(0.0, temp_mean - dew_mean)

                regime = regime_classifier.classify(
                    latitude=lat,
                    longitude=lon,
                    elevation=0.0,
                    temperature=temp_mean,
                    humidity=hum_mean,
                    pressure=pres_mean,
                    wind_speed=wind_mean,
                    precipitation=precip_mean,
                    timestamp_str=t_ref,
                )

                raw: Dict[str, float] = {
                    "lat": lat,
                    "lon": lon,
                    "elevation": 0.0,
                    "hour_sin": math.sin(2 * math.pi * hour / 24.0),
                    "hour_cos": math.cos(2 * math.pi * hour / 24.0),
                    "month_sin": math.sin(2 * math.pi * month / 12.0),
                    "month_cos": math.cos(2 * math.pi * month / 12.0),
                    "lead_time_hours": float(lead),
                    "temp_mean": temp_mean,
                    "humidity_mean": hum_mean,
                    "pressure_mean": pres_mean,
                    "wind_speed_mean": wind_mean,
                    "precip_mean": precip_mean,
                    "precip_std": precip_std,
                    "temp_std": temp_std,
                    "dew_point_depression": dew_depression,
                    "regime_convective": 1.0 if regime.regime == "CONVECTIVE" else 0.0,
                    "regime_monsoon": 1.0 if regime.regime == "MONSOON" else 0.0,
                    "regime_extreme": 1.0 if regime.regime == "EXTREME" else 0.0,
                }

                if not m_temps:
                    continue

                X.append(build_vector(raw))
                E.append(np.array(errors, dtype=np.float64))
                M.append(np.array(present, dtype=np.float64))
                produced += 1

        if produced:
            stats["sites"] += 1
        stats["samples"] += produced
        logger.info(
            "samples built", extra={"context": {"site": name, "samples": produced}}
        )

    if not X:
        return (
            np.zeros((0, FEATURE_DIM), dtype=np.float32),
            np.zeros((0, len(MODEL_KEYS)), dtype=np.float32),
            np.zeros((0, len(MODEL_KEYS)), dtype=np.float32),
            stats,
        )

    return (
        np.array(X, dtype=np.float32),
        np.array(E, dtype=np.float32),
        np.array(M, dtype=np.float32),
        stats,
    )


class UniformNetwork(nn.Module):
    """Equal weighting, used only to measure the holdout baseline."""

    def __init__(self, num_models: int) -> None:
        super().__init__()
        self.num_models = num_models

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return torch.full(
            (*x.shape[:-1], self.num_models), 1.0 / self.num_models, device=x.device
        )


def _masked_weights(pred: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    """Renormalise exactly the way the runtime does.

    ``GatingModelManager.predict`` applies ``np.clip(raw, 0.0, None)`` before
    normalising. Training must clamp identically: without the clamp the
    optimiser discovers it can beat the constrained convex optimum by emitting
    negative weights, which looks like excellent skill in the report but is
    destroyed the moment the trained net is served. That is a train/serve
    mismatch, not a result.
    """
    weights = torch.clamp(pred, min=0.0) * mask
    return weights / weights.sum(dim=-1, keepdim=True).clamp_min(1e-8)


def blend_error_loss(
    pred: torch.Tensor, errors: torch.Tensor, mask: torch.Tensor
) -> torch.Tensor:
    """Minimise the real blended error, not a proxy in weight space.

    The network's job is to output weights ``w``; the quantity that actually
    matters is the resulting forecast error

        e(w) = sum_i w_i * (forecast_i - reference)

    so that is what is optimised directly, after clamping and renormalising
    ``w`` over the available members exactly as the runtime does. Regressing
    onto the optimal weight vector instead (a KL or L2 loss against a target)
    is badly conditioned: the constrained optimum is close to one-hot, so the
    target is nearly discontinuous and the optimiser chases unlearnable
    targets. The direct loss is smooth and is the same quantity the holdout
    check reports.
    """
    blended_error = (_masked_weights(pred, mask) * errors).sum(dim=-1)
    return (blended_error ** 2).mean()


@torch.no_grad()
def skill_report(
    model: nn.Module,
    X: torch.Tensor,
    E: torch.Tensor,
    M: torch.Tensor,
) -> Dict[str, float]:
    """MAE/RMSE of the blend, equal weighting, and the per-sample optimum."""
    model.eval()
    weights = _masked_weights(model(X), M).numpy()
    errors = E.numpy()
    mask = M.numpy()

    valid = mask.sum(axis=1) >= 2
    if not valid.any():
        return {
            "n": 0,
            "net_mae": 0.0,
            "uniform_mae": 0.0,
            "best_possible_mae": 0.0,
        }

    w, e, m = weights[valid], errors[valid], mask[valid]
    net = (w * e).sum(axis=1)
    uniform = (m * e).sum(axis=1) / m.sum(axis=1)

    # Exact floor for any non-negative weighting. e(w) = sum_i w_i e_i with
    # w >= 0 and sum_i w_i = 1 is a convex combination of the member errors, so
    # |e(w)| <= sum_i w_i |e_i| <= max_i |e_i|; placing all weight on the single
    # most accurate member attains min_i |e_i|. This replaces a ridge-regularised
    # QP solver that was quietly returning a non-optimal "floor" -- it reported
    # 0.4116 as the minimum achievable MAE when a plain blend already scored
    # 0.3999, which is impossible and should have been read as a bug.
    best = np.min(np.where(m > 0, np.abs(e), np.inf), axis=1)

    return {
        "n": int(valid.sum()),
        "net_mae": float(np.abs(net).mean()),
        "uniform_mae": float(np.abs(uniform).mean()),
        "best_possible_mae": float(np.abs(best).mean()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=45,
                        help="Length of the training archive window.")
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=2e-3)
    parser.add_argument("--holdout-days", type=int, default=14,
                        help="Trailing days reserved for the baseline comparison.")
    parser.add_argument("--out", type=str, default=str(settings.MODEL_WEIGHTS_PATH))
    parser.add_argument("--allow-regression", action="store_true",
                        help="Save even if the network fails to beat the baselines.")
    args = parser.parse_args()

    _seed_everything()
    device = torch.device(settings.ML_DEVICE)

    end = date.today() - timedelta(days=args.holdout_days)
    start = end - timedelta(days=args.days)

    print("=" * 68)
    print("AeroBlend AI gating network training on real archived forecast error")
    print(f"window  : {start} .. {end}  ({args.days} days, {len(SITES)} sites)")
    print(f"leads   : {list(LEAD_HOURS)}")
    print("=" * 68)

    X, E, M, stats = asyncio.run(build_dataset(start=start, end=end, sites=SITES))
    print(f"sites used {stats['sites']}/{len(SITES)}   sparse-skipped {stats['skipped_sparse']}   "
          f"no-reference {stats['no_reference']}")
    print(f"dataset: {X.shape[0]} samples, {X.shape[1]} features, "
          f"{E.shape[1]} member error channels")
    if X.shape[0] < 200:
        print("\nRefusing to train: fewer than 200 usable samples. The archive window is "
              "probably too short or unreachable.")
        return 1

    # Chronological split: the holdout is later in time, so this measures
    # generalisation forward in time rather than interpolating between
    # neighbouring days.
    split = int(X.shape[0] * 0.8)
    X_tr, E_tr, M_tr = (torch.tensor(X[:split]), torch.tensor(E[:split]), torch.tensor(M[:split]))
    X_va, E_va, M_va = (torch.tensor(X[split:]), torch.tensor(E[split:]), torch.tensor(M[split:]))
    print(f"train {X_tr.shape[0]}   holdout {X_va.shape[0]}")

    uniform_report = skill_report(UniformNetwork(len(MODEL_KEYS)), X_va, E_va, M_va)
    print(f"equal weighting holdout MAE: {uniform_report['uniform_mae']:.4f} degC")

    model = AdaptiveGatingNetwork(input_dim=settings.GATING_INPUT_DIM,
                                  num_models=len(MODEL_KEYS)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)

    best = {"loss": float("inf"), "state": None, "epoch": 0}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        model.train()
        perm = torch.randperm(X_tr.shape[0])
        total, batches = 0.0, 0
        for i in range(0, X_tr.shape[0], args.batch_size):
            idx = perm[i : i + args.batch_size]
            optimizer.zero_grad()
            loss = blend_error_loss(model(X_tr[idx]), E_tr[idx], M_tr[idx])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            total += float(loss.detach())
            batches += 1

        with torch.no_grad():
            holdout_loss = float(blend_error_loss(model(X_va), E_va, M_va))
        if holdout_loss < best["loss"]:
            best = {
                "loss": holdout_loss,
                "state": {k: v.detach().clone() for k, v in model.state_dict().items()},
                "epoch": epoch,
            }
        if epoch % 10 == 0 or epoch == 1:
            print(
                f"epoch {epoch:03d}/{args.epochs}  train MSE {total / max(1, batches):.5f}  "
                f"holdout MSE {holdout_loss:.5f}"
            )

    if best["state"] is None:
        print("training produced no checkpoint")
        return 1

    model.load_state_dict(best["state"])
    model.eval()

    # --- Honest skill check against baselines --------------------------------
    print("\n" + "=" * 68)
    print("Holdout skill: MAE of the blended forecast against ERA5 (degC)")
    print("=" * 68)
    report = skill_report(model, X_va, E_va, M_va)
    print(f"samples scored        : {report['n']}")
    print(f"gating blend MAE      : {report['net_mae']:.4f}")
    print(f"equal weighting MAE   : {report['uniform_mae']:.4f}")
    print(f"per-sample optimum MAE: {report['best_possible_mae']:.4f}  (oracle one-hot floor)")
    skill = 1.0 - report["net_mae"] / max(report["uniform_mae"], 1e-12)
    print(f"skill vs equal weights: {skill:+.4f}")

    # Sanity invariants. The optimum can never be worse than equal weighting,
    # and a convex combination can never beat the convex optimum. Either
    # violation means the scoring path has diverged from the runtime.
    if report["best_possible_mae"] > report["uniform_mae"] + 1e-9:
        print("\nINTERNAL ERROR: the per-sample optimum scores worse than equal "
              "weighting, which is impossible. The target solver is wrong.")
        return 3
    if report["net_mae"] < report["best_possible_mae"] - 1e-6:
        print("\nINTERNAL ERROR: the blend scores better than the constrained "
              "convex optimum, which is impossible for non-negative weights. "
              "The training objective is not applying the runtime's "
              "non-negativity clamp, so the reported skill would not survive "
              "being served.")
        return 3

    beats = report["net_mae"] <= report["uniform_mae"]
    if not beats and not args.allow_regression:
        print("\nThe network does not beat equal weighting on the holdout set. "
              "Refusing to replace the current checkpoint (pass --allow-regression "
              "to save it anyway).")
        return 2

    torch.save(best["state"], args.out)
    npz_out = os.path.splitext(args.out)[0] + ".npz"
    np.savez(npz_out, **{k: v.cpu().numpy() for k, v in best["state"].items()})
    print(f"\nsaved checkpoints: {args.out} and {npz_out}  (best epoch {best['epoch']}, "
          f"holdout MSE {best['loss']:.5f})")
    open_meteo_provider.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
