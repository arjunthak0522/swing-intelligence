from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StateTerm:
    feature: str
    op: str
    threshold: float


@dataclass(frozen=True)
class StateHypothesis:
    name: str
    terms: tuple[StateTerm, ...]
    rationale: str
    family: str


def add_market_state_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add interpretable, causal market-state features using only information known at each date."""
    out = frame.copy()
    close = pd.to_numeric(out["close"], errors="coerce")

    out["return_3d"] = close.pct_change(3)
    out["drawdown_20d"] = close / close.rolling(20).max() - 1.0
    out["drawdown_60d"] = close / close.rolling(60).max() - 1.0
    out["drawdown_252d"] = close / close.rolling(252).max() - 1.0
    out["rebound_3d"] = out["return_3d"]
    out["momentum_accel_5v20"] = out["return_5d"] - (out["return_20d"] / 4.0)

    rv10 = pd.to_numeric(out.get("realized_vol_10"), errors="coerce")
    rv20 = pd.to_numeric(out.get("realized_vol_20"), errors="coerce")
    out["vol_expansion_ratio"] = rv10 / rv20.replace(0, np.nan)

    if "gap_sma_20" in out:
        gap20 = pd.to_numeric(out["gap_sma_20"], errors="coerce")
        out["trend_repair_5d"] = gap20 - gap20.shift(5)
        out["abs_gap_sma_20"] = gap20.abs()

    if "vix_change_5d" in out:
        out["vix_cooling_5d"] = -pd.to_numeric(out["vix_change_5d"], errors="coerce")

    return out


def _q(train: pd.DataFrame, feature: str, q: float) -> float | None:
    if feature not in train:
        return None
    s = pd.to_numeric(train[feature], errors="coerce").dropna()
    if len(s) < 100 or s.nunique() < 20:
        return None
    return float(s.quantile(q))


def _term(train: pd.DataFrame, feature: str, op: str, q: float) -> StateTerm | None:
    threshold = _q(train, feature, q)
    if threshold is None:
        return None
    return StateTerm(feature, op, threshold)


def _make(name: str, family: str, rationale: str, *terms: StateTerm | None) -> StateHypothesis | None:
    if any(t is None for t in terms):
        return None
    return StateHypothesis(name=name, terms=tuple(terms), rationale=rationale, family=family)  # type: ignore[arg-type]


def learn_market_state_hypotheses(train: pd.DataFrame, target: str) -> list[StateHypothesis]:
    """Create a small semantic hypothesis library with thresholds frozen from training data only.

    These are market-state templates, not optimized rules. Quantiles determine only the
    numeric boundary for a predeclared economic state.
    """
    target = target.upper()
    candidates = [
        _make(
            "pullback_with_rebound",
            "pullback_recovery",
            "Meaningful 52-week drawdown while short-term price action has begun to rebound.",
            _term(train, "drawdown_252d", "<=", 0.20),
            _term(train, "rebound_3d", ">=", 0.70),
        ),
        _make(
            "deep_pullback_momentum_stabilizing",
            "pullback_recovery",
            "Deep drawdown with improving short-versus-medium-term momentum.",
            _term(train, "drawdown_252d", "<=", 0.10),
            _term(train, "momentum_accel_5v20", ">=", 0.70),
        ),
        _make(
            "oversold_trend_repair",
            "trend_repair",
            "Price remains weak versus its 20-day trend but that trend gap is repairing quickly.",
            _term(train, "gap_sma_20", "<=", 0.20),
            _term(train, "trend_repair_5d", ">=", 0.80),
        ),
        _make(
            "volatility_shock_cooling",
            "volatility_normalization",
            "Volatility remains elevated while VIX has started cooling from the shock.",
            _term(train, "vix_percentile_252", ">=", 0.80),
            _term(train, "vix_cooling_5d", ">=", 0.60),
        ),
        _make(
            "price_weakness_with_vol_cooling",
            "volatility_normalization",
            "Price is in a meaningful drawdown while volatility pressure is easing.",
            _term(train, "drawdown_60d", "<=", 0.20),
            _term(train, "vix_cooling_5d", ">=", 0.60),
        ),
        _make(
            "volatility_compression_near_trend",
            "compression",
            "Short-run realized volatility is compressed and price is close to its 20-day trend.",
            _term(train, "vol_expansion_ratio", "<=", 0.20),
            _term(train, "abs_gap_sma_20", "<=", 0.40),
        ),
        _make(
            "momentum_acceleration_after_weakness",
            "momentum_turn",
            "Medium-term performance is weak but recent momentum is accelerating materially.",
            _term(train, "return_20d", "<=", 0.30),
            _term(train, "momentum_accel_5v20", ">=", 0.80),
        ),
        _make(
            "trend_repair_with_vol_expansion",
            "trend_repair",
            "Price trend is repairing while short-run volatility expands, consistent with a forceful reversal attempt.",
            _term(train, "trend_repair_5d", ">=", 0.80),
            _term(train, "vol_expansion_ratio", ">=", 0.70),
        ),
        _make(
            "credit_stress_cooling",
            "credit_normalization",
            "High-yield credit spreads remain elevated but have started narrowing.",
            _term(train, "hy_spread_percentile_252", ">=", 0.70),
            _term(train, "hy_spread_cooling_5d", ">=", 0.60),
        ),
        _make(
            "rates_easing_with_rebound",
            "rates_relief",
            "Equities are rebounding while the 10-year Treasury yield has eased over the prior month.",
            _term(train, "rebound_3d", ">=", 0.70),
            _term(train, "yield_10y_change_20d", "<=", 0.35),
        ),
        _make(
            "curve_resteepening_with_rebound",
            "curve_repair",
            "Equities are rebounding while the 10Y-2Y curve is re-steepening.",
            _term(train, "rebound_3d", ">=", 0.70),
            _term(train, "yield_curve_change_20d", ">=", 0.65),
        ),
        _make(
            "credit_and_volatility_cooling",
            "risk_normalization",
            "Both credit stress and equity volatility are cooling after elevated risk conditions.",
            _term(train, "hy_spread_cooling_5d", ">=", 0.60),
            _term(train, "vix_cooling_5d", ">=", 0.60),
        ),
    ]

    if target == "SPY":
        candidates.extend([
            _make(
                "spy_pullback_breadth_resilience",
                "breadth_divergence",
                "SPY is weak while equal-weight relative strength is resilient.",
                _term(train, "drawdown_60d", "<=", 0.20),
                _term(train, "rsp_spy_ret_20d", ">=", 0.70),
            ),
            _make(
                "spy_rebound_with_breadth_confirmation",
                "breadth_confirmation",
                "SPY is rebounding and equal-weight breadth is confirming the recovery.",
                _term(train, "rebound_3d", ">=", 0.70),
                _term(train, "rsp_spy_ret_5d", ">=", 0.70),
            ),
            _make(
                "spy_breadth_credit_recovery",
                "breadth_credit_confirmation",
                "SPY rebound is confirmed by equal-weight leadership and cooling credit stress.",
                _term(train, "rebound_3d", ">=", 0.70),
                _term(train, "rsp_spy_ret_5d", ">=", 0.65),
                _term(train, "hy_spread_cooling_5d", ">=", 0.60),
            ),
        ])

    if target == "QQQ":
        candidates.extend([
            _make(
                "qqq_pullback_semiconductor_resilience",
                "leadership_divergence",
                "QQQ is weak while semiconductor leadership remains relatively resilient.",
                _term(train, "drawdown_60d", "<=", 0.20),
                _term(train, "smh_qqq_ret_20d", ">=", 0.70),
            ),
            _make(
                "qqq_rebound_with_semiconductor_confirmation",
                "leadership_confirmation",
                "QQQ is rebounding with semiconductor relative strength confirming the move.",
                _term(train, "rebound_3d", ">=", 0.70),
                _term(train, "smh_qqq_ret_5d", ">=", 0.70),
            ),
            _make(
                "qqq_rates_credit_relief",
                "growth_macro_relief",
                "QQQ is rebounding while long yields ease and high-yield credit stress cools.",
                _term(train, "rebound_3d", ">=", 0.65),
                _term(train, "yield_10y_change_20d", "<=", 0.35),
                _term(train, "hy_spread_cooling_5d", ">=", 0.60),
            ),
            _make(
                "qqq_semis_rates_relief",
                "growth_leadership_macro",
                "QQQ rebound is confirmed by semiconductor leadership while long yields ease.",
                _term(train, "rebound_3d", ">=", 0.65),
                _term(train, "smh_qqq_ret_5d", ">=", 0.65),
                _term(train, "yield_10y_change_20d", "<=", 0.35),
            ),
        ])

    return [c for c in candidates if c is not None]