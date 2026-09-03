from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

from .outcomes import forward_path_stats


@dataclass(frozen=True)
class BootstrapResult:
    observed_median_edge: float
    ci_low: float
    ci_high: float
    p_value_one_sided: float
    n: int


def _block_sample(arr: np.ndarray, n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    if len(arr) == 0:
        return np.array([], dtype=float)
    parts = []
    while sum(len(x) for x in parts) < n:
        start = int(rng.integers(0, max(1, len(arr) - block + 1)))
        parts.append(arr[start:start + block])
    return np.concatenate(parts)[:n]


def block_bootstrap_edge(signal_returns: pd.Series, baseline_returns: pd.Series, *, iterations: int = 2000,
                         block: int = 5, seed: int = 7) -> BootstrapResult:
    """Bootstrap difference in medians while preserving short-run dependence in blocks."""
    s = pd.Series(signal_returns).dropna().to_numpy(float)
    b = pd.Series(baseline_returns).dropna().to_numpy(float)
    if len(s) < 20 or len(b) < 100:
        raise ValueError("Insufficient observations for bootstrap")
    observed = float(np.median(s) - np.median(b))
    rng = np.random.default_rng(seed)
    diffs = np.empty(iterations)
    for i in range(iterations):
        ss = _block_sample(s, len(s), block, rng)
        bb = _block_sample(b, len(b), block, rng)
        diffs[i] = np.median(ss) - np.median(bb)
    low, high = np.quantile(diffs, [0.025, 0.975])
    p = float((np.sum(diffs <= 0) + 1) / (iterations + 1))
    return BootstrapResult(observed, float(low), float(high), p, len(s))


def benjamini_hochberg(p_values: dict[str, float], alpha: float = 0.05) -> pd.DataFrame:
    """FDR control across a family of researched hypotheses."""
    if not p_values:
        return pd.DataFrame(columns=["signal", "p_value", "bh_threshold", "passes_fdr"])
    rows = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(rows)
    out = []
    kmax = 0
    for rank, (name, p) in enumerate(rows, start=1):
        thr = alpha * rank / m
        if p <= thr:
            kmax = rank
        out.append({"signal": name, "p_value": float(p), "bh_threshold": thr, "rank": rank})
    for row in out:
        row["passes_fdr"] = row["rank"] <= kmax and kmax > 0
    return pd.DataFrame(out)


def forward_close_returns(df: pd.DataFrame, dates, horizon: int) -> pd.Series:
    stats = forward_path_stats(df, dates, horizon)
    if stats.empty:
        return pd.Series(dtype=float)
    return stats["forward_return"].reset_index(drop=True)
