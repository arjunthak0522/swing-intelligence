from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from .outcomes import forward_path_stats
from .robustness import block_bootstrap_edge, benjamini_hochberg
from .tournament import SignalSpec


@dataclass(frozen=True)
class EvidenceConfig:
    horizon: int = 10
    min_n: int = 30
    bootstrap_iterations: int = 1000
    bootstrap_block: int = 5
    fdr_alpha: float = 0.05


def _summarize_returns(paths: pd.DataFrame) -> tuple[pd.Series, float, float, float]:
    if paths.empty:
        return pd.Series(dtype=float), np.nan, np.nan, np.nan
    r = paths["forward_return"].dropna().astype(float)
    if r.empty:
        return r, np.nan, np.nan, np.nan
    return r, float(r.median()), float((r > 0).mean()), float(paths["mae"].median())


def prior_only_signal_evidence(
    df: pd.DataFrame,
    signal: SignalSpec,
    *,
    as_of,
    config: EvidenceConfig = EvidenceConfig(),
) -> dict | None:
    """Compute one signal's evidence using only observations strictly before as_of.

    The current signal may be observed on `as_of`, but its historical statistics
    are calculated only from earlier dates. Forward paths that cannot be fully
    observed inside that prior history are naturally excluded.
    """
    as_of = pd.Timestamp(as_of)
    prior = df.loc[df.index < as_of]
    if len(prior) <= config.horizon + 5:
        return None
    hist_mask = signal.mask.reindex(prior.index).fillna(False)
    entries = prior.index[hist_mask]
    conditional = forward_path_stats(prior, entries, config.horizon)
    baseline = forward_path_stats(prior, prior.index, config.horizon)
    sret, smedian, swin, smae = _summarize_returns(conditional)
    bret, bmedian, bwin, _ = _summarize_returns(baseline)
    if len(sret) < config.min_n or len(bret) < 100:
        return None
    boot = block_bootstrap_edge(
        sret,
        bret,
        iterations=config.bootstrap_iterations,
        block=config.bootstrap_block,
        seed=7,
    )
    return {
        "signal": signal.name,
        "n": int(len(sret)),
        "median_return": smedian,
        "normal_median_return": bmedian,
        "median_excess_edge": float(smedian - bmedian),
        "win_probability": swin,
        "normal_win_probability": bwin,
        "win_edge": float(swin - bwin),
        "median_mae": smae,
        "ci_low": float(boot.ci_low),
        "ci_high": float(boot.ci_high),
        "p_value": float(boot.p_value_one_sided),
    }


def evidence_snapshot(
    df: pd.DataFrame,
    signals: Iterable[SignalSpec],
    *,
    as_of,
    asset: str,
    stable_signals: Mapping[str, bool] | None = None,
    config: EvidenceConfig = EvidenceConfig(),
) -> pd.DataFrame:
    """Return dated evidence for signals active on as_of, with family-wise FDR."""
    as_of = pd.Timestamp(as_of)
    rows: list[dict] = []
    pvals: dict[str, float] = {}
    stable_signals = stable_signals or {}
    for signal in signals:
        current = signal.mask.reindex(df.index).fillna(False)
        if as_of not in current.index or not bool(current.loc[as_of]):
            continue
        row = prior_only_signal_evidence(df, signal, as_of=as_of, config=config)
        if row is None:
            continue
        row.update({
            "date": as_of,
            "asset": asset.upper(),
            "stable": bool(stable_signals.get(signal.name, False)),
        })
        rows.append(row)
        pvals[signal.name] = row["p_value"]
    if not rows:
        return pd.DataFrame()
    fdr = benjamini_hochberg(pvals, alpha=config.fdr_alpha).set_index("signal")
    out = pd.DataFrame(rows)
    out["passes_fdr"] = out["signal"].map(fdr["passes_fdr"]).fillna(False).astype(bool)
    return out


def best_asset_evidence(snapshot: pd.DataFrame) -> pd.DataFrame:
    """Collapse signal-level evidence to one strongest qualifying row per asset.

    This is not a score. It preserves the signal with the strongest positive
    lower confidence bound; ties use less-negative MAE and then signal name.
    """
    if snapshot.empty:
        return snapshot.copy()
    rows = []
    for asset, group in snapshot.groupby("asset", sort=True):
        eligible = group.loc[
            group["passes_fdr"]
            & group["stable"]
            & (group["ci_low"] > 0)
            & (group["win_edge"] > 0)
        ].copy()
        if eligible.empty:
            continue
        best = eligible.sort_values(
            ["ci_low", "median_mae", "signal"],
            ascending=[False, False, True],
        ).iloc[0]
        rows.append(best)
    return pd.DataFrame(rows).reset_index(drop=True) if rows else pd.DataFrame(columns=snapshot.columns)
