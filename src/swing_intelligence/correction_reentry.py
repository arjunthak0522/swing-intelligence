from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .opportunity_score import calibrated_opportunity_score
from .walk_forward import _folds


@dataclass(frozen=True)
class CorrectionReentryConfig:
    first_test_year: int = 2010
    fold_years: int = 2
    score_trigger: float = 70.0
    headline_drawdown: float = -0.05
    episode_min_gap_days: int = 20
    max_signal_wait_days: int = 20
    horizons: tuple[int, ...] = (10, 20, 30, 60)
    comparison_delays: tuple[int, ...] = (0, 3, 5, 10)
    transaction_cost_bps: float = 10.0


def _score_series(features: pd.DataFrame, config: CorrectionReentryConfig) -> pd.Series:
    out = pd.Series(np.nan, index=features.index, dtype=float)
    for _, _, test_start, test_end in _folds(pd.DatetimeIndex(features.index), config):
        train = features.loc[features.index < test_start]
        test = features.loc[(features.index >= test_start) & (features.index <= test_end)]
        if len(train) < 252 * 5 or len(test) < 2:
            continue
        out.loc[test.index] = calibrated_opportunity_score(train, test, "SPY")["opportunity_score"]
    return out


def correction_state(features: pd.DataFrame, config: CorrectionReentryConfig) -> pd.DataFrame:
    close = pd.to_numeric(features["close"], errors="coerce")
    dd60 = close / close.rolling(60).max() - 1.0
    rsp = pd.to_numeric(features.get("rsp_spy_ret_20d", np.nan), errors="coerce")
    iwm = pd.to_numeric(features.get("iwm_spy_ret_20d", np.nan), errors="coerce")
    vix_z = pd.to_numeric(features.get("vix_z_60", np.nan), errors="coerce")
    vix5 = pd.to_numeric(features.get("vix_change_5d", np.nan), errors="coerce")

    headline = dd60 <= config.headline_drawdown
    rolling = (~headline) & (rsp <= -0.015) & (iwm <= -0.02)
    internal = (~headline) & (~rolling) & (((rsp <= -0.01) & (vix_z >= 1.0)) | ((iwm <= -0.015) & (vix5 >= 0.15)))
    active = headline | rolling | internal

    typ = pd.Series("none", index=features.index, dtype=object)
    typ.loc[internal] = "internal"
    typ.loc[rolling] = "rolling"
    typ.loc[headline] = "headline"
    return pd.DataFrame({"drawdown_60d": dd60, "headline": headline, "rolling": rolling, "internal": internal, "active": active, "type": typ}, index=features.index)


def _episode_onsets(state: pd.DataFrame, config: CorrectionReentryConfig) -> list[int]:
    active = state["active"].fillna(False).to_numpy(dtype=bool)
    starts = np.where(active & ~np.r_[False, active[:-1]])[0].tolist()
    kept: list[int] = []
    for p in starts:
        if not kept or p - kept[-1] >= config.episode_min_gap_days:
            kept.append(p)
    return kept


def _entry_return(features: pd.DataFrame, entry_pos: int, horizon: int, cost_bps: float) -> float:
    exit_pos = entry_pos + horizon
    if entry_pos >= len(features) or exit_pos >= len(features):
        return np.nan
    op = float(features["open"].iloc[entry_pos])
    cl = float(features["close"].iloc[exit_pos])
    if not np.isfinite(op) or not np.isfinite(cl) or op <= 0:
        return np.nan
    return float((cl / op) * (1.0 - cost_bps / 10000.0) - 1.0)


def _mae(features: pd.DataFrame, entry_pos: int, horizon: int) -> float:
    end = min(entry_pos + horizon, len(features) - 1)
    op = float(features["open"].iloc[entry_pos])
    lows = pd.to_numeric(features["low"].iloc[entry_pos:end+1], errors="coerce")
    if not np.isfinite(op) or op <= 0 or lows.dropna().empty:
        return np.nan
    return float(lows.min() / op - 1.0)


def run_correction_reentry_validation(features: pd.DataFrame, config: CorrectionReentryConfig = CorrectionReentryConfig()) -> dict:
    features = features.sort_index().copy()
    idx = pd.DatetimeIndex(features.index)
    state = correction_state(features, config)
    score = _score_series(features, config)
    onsets = _episode_onsets(state, config)
    rows = []

    for onset_pos in onsets:
        onset_date = idx[onset_pos]
        if onset_date.year < config.first_test_year:
            continue
        max_needed = max(max(config.horizons), config.max_signal_wait_days + 1, max(config.comparison_delays) + 1)
        if onset_pos + max_needed >= len(features):
            continue

        search_end = min(onset_pos + config.max_signal_wait_days, len(features) - 2)
        window = score.iloc[onset_pos:search_end+1]
        hits = window[window >= config.score_trigger]
        if len(hits):
            signal_date = pd.Timestamp(hits.index[0])
            signal_pos = int(features.index.get_loc(signal_date))
            signal_entry = signal_pos + 1
            signal_found = True
        else:
            signal_date = pd.NaT
            signal_entry = None
            signal_found = False

        local_end = min(onset_pos + config.max_signal_wait_days, len(features) - 1)
        local_slice = pd.to_numeric(features["low"].iloc[onset_pos:local_end+1], errors="coerce")
        low_pos = int(features.index.get_loc(local_slice.idxmin())) if not local_slice.dropna().empty else onset_pos

        row = {
            "onset_date": str(onset_date.date()),
            "correction_type": str(state["type"].iloc[onset_pos]),
            "onset_drawdown_60d": float(state["drawdown_60d"].iloc[onset_pos]),
            "signal_found": signal_found,
            "signal_date": None if pd.isna(signal_date) else str(signal_date.date()),
            "signal_delay_days": None if signal_entry is None else int(signal_entry - onset_pos),
            "local_low_date": str(idx[low_pos].date()),
            "signal_distance_from_low_days": None if signal_entry is None else int(signal_entry - low_pos),
        }
        for h in config.horizons:
            if signal_entry is not None:
                row[f"signal_return_{h}d"] = _entry_return(features, signal_entry, h, config.transaction_cost_bps)
                row[f"signal_mae_{h}d"] = _mae(features, signal_entry, h)
            else:
                row[f"signal_return_{h}d"] = np.nan
                row[f"signal_mae_{h}d"] = np.nan
            for d in config.comparison_delays:
                entry = onset_pos + d + 1
                row[f"delay_{d}_return_{h}d"] = _entry_return(features, entry, h, config.transaction_cost_bps)
            oracle_entry = min(low_pos + 1, len(features)-1)
            row[f"local_low_oracle_return_{h}d"] = _entry_return(features, oracle_entry, h, config.transaction_cost_bps)
        rows.append(row)

    df = pd.DataFrame(rows)
    summary: dict[str, object] = {"episode_count": int(len(df))}
    if not df.empty:
        signaled = df[df["signal_found"]].copy()
        summary["signal_episode_count"] = int(len(signaled))
        summary["signal_fraction"] = float(len(signaled) / len(df))
        summary["type_counts"] = {str(k): int(v) for k, v in df["correction_type"].value_counts().to_dict().items()}
        if len(signaled):
            summary["median_signal_delay_days"] = float(signaled["signal_delay_days"].median())
            summary["median_signal_distance_from_low_days"] = float(signaled["signal_distance_from_low_days"].median())
            horizon_stats = {}
            for h in config.horizons:
                s = signaled[f"signal_return_{h}d"].astype(float)
                stats = {"median_signal_return": float(s.median()), "win_rate": float((s > 0).mean()), "median_mae": float(signaled[f"signal_mae_{h}d"].median())}
                for d in config.comparison_delays:
                    b = signaled[f"delay_{d}_return_{h}d"].astype(float)
                    diff = s - b
                    stats[f"median_edge_vs_delay_{d}"] = float(diff.median())
                    stats[f"win_rate_vs_delay_{d}"] = float((diff > 0).mean())
                horizon_stats[str(h)] = stats
            summary["horizons"] = horizon_stats
    return {"config": asdict(config), "summary": summary, "rows": rows}
