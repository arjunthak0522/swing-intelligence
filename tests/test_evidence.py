import numpy as np
import pandas as pd

from swing_intelligence.evidence import EvidenceConfig, prior_only_signal_evidence, best_asset_evidence
from swing_intelligence.tournament import SignalSpec


def test_prior_only_evidence_does_not_use_as_of_future():
    rng = np.random.default_rng(3)
    idx = pd.date_range("2018-01-01", periods=900, freq="B")
    ret = rng.normal(.0003, .01, len(idx))
    close = 100 * np.cumprod(1 + ret)
    df = pd.DataFrame({
        "open": close,
        "high": close * 1.005,
        "low": close * .995,
        "close": close,
        "volume": 1_000_000,
    }, index=idx)
    mask = pd.Series(False, index=idx)
    mask.iloc[::5] = True
    sig = SignalSpec("every5", mask)
    as_of = idx[-20]
    cfg = EvidenceConfig(horizon=5, min_n=30, bootstrap_iterations=100)
    first = prior_only_signal_evidence(df, sig, as_of=as_of, config=cfg)
    df2 = df.copy()
    df2.loc[df2.index >= as_of, ["open", "high", "low", "close"]] *= 10
    second = prior_only_signal_evidence(df2, sig, as_of=as_of, config=cfg)
    assert first is not None and second is not None
    assert first["median_excess_edge"] == second["median_excess_edge"]
    assert first["ci_low"] == second["ci_low"]


def test_best_asset_evidence_uses_lower_bound_not_score():
    snap = pd.DataFrame([
        [pd.Timestamp("2025-01-02"), "QQQ", "a", 50, .010, .02, -.03, True, True],
        [pd.Timestamp("2025-01-02"), "QQQ", "b", 60, .015, .01, -.04, True, True],
        [pd.Timestamp("2025-01-02"), "SPY", "c", 80, .008, .03, -.01, True, True],
    ], columns=["date","asset","signal","n","ci_low","win_edge","median_mae","passes_fdr","stable"])
    best = best_asset_evidence(snap)
    q = best.loc[best.asset == "QQQ"].iloc[0]
    assert q.signal == "b"
