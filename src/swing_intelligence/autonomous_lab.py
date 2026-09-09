from __future__ import annotations

from dataclasses import dataclass, asdict, replace
from typing import Iterable

import numpy as np
import pandas as pd

from .outcomes import summarize_forward_paths
from .research import ResearchSplit, add_research_features, split_periods


DEFAULT_HORIZONS = (1, 5, 10, 20, 30, 60, 120)

DISCOVERY_FEATURES = (
    "return_5d", "return_10d", "return_20d",
    "gap_sma_20", "gap_sma_50", "gap_sma_200", "sma20_slope_5d",
    "rsi_5", "rsi_14", "zscore_20", "drawdown_5d",
    "realized_vol_10", "realized_vol_20", "downside_vol_20",
    "atr_pct", "atr_pct_rank_252", "volume_z_20",
    "rsp_spy_ret_5d", "rsp_spy_ret_20d",
    "qqq_spy_ret_5d", "qqq_spy_ret_20d",
    "iwm_spy_ret_5d", "iwm_spy_ret_20d",
    "smh_qqq_ret_5d", "smh_qqq_ret_20d",
    "vix_level", "vix_change_1d", "vix_change_5d", "vix_z_60", "vix_percentile_252",
)

PRICE_STATE_FEATURES = {
    "return_5d", "return_10d", "return_20d",
    "gap_sma_20", "gap_sma_50", "gap_sma_200", "sma20_slope_5d",
    "rsi_5", "rsi_14", "zscore_20", "drawdown_5d",
}
CONTEXT_FEATURES = set(DISCOVERY_FEATURES) - PRICE_STATE_FEATURES


@dataclass(frozen=True)
class LabConfig:
    horizons: tuple[int, ...] = DEFAULT_HORIZONS
    primary_horizon: int = 30
    min_n: int = 25
    quantiles: tuple[float, ...] = (0.10, 0.20, 0.80, 0.90)
    max_pair_rules: int = 250
    min_validation_edge: float = 0.0
    min_holdout_edge: float = 0.0
    min_validation_win_edge: float = 0.0
    min_holdout_win_edge: float = 0.0


@dataclass(frozen=True)
class RuleTerm:
    feature: str
    op: str
    threshold: float

    def apply(self, frame: pd.DataFrame) -> pd.Series:
        if self.feature not in frame:
            return pd.Series(False, index=frame.index)
        s = pd.to_numeric(frame[self.feature], errors="coerce")
        if self.op == "<=":
            return s <= self.threshold
        if self.op == ">=":
            return s >= self.threshold
        raise ValueError(f"Unsupported operator: {self.op}")


@dataclass(frozen=True)
class HypothesisRule:
    name: str
    terms: tuple[RuleTerm, ...]
    rationale: str

    def mask(self, frame: pd.DataFrame) -> pd.Series:
        out = pd.Series(True, index=frame.index)
        for term in self.terms:
            out &= term.apply(frame).fillna(False)
        return out.fillna(False)


def _eligible_features(train: pd.DataFrame) -> list[str]:
    return [
        c for c in DISCOVERY_FEATURES
        if c in train.columns and pd.api.types.is_numeric_dtype(train[c]) and train[c].notna().sum() >= 100
    ]


def learn_hypotheses(full_features: pd.DataFrame, split: ResearchSplit = ResearchSplit(), config: LabConfig = LabConfig()) -> list[HypothesisRule]:
    """Generate fixed hypotheses from training data only."""
    train = split_periods(full_features, split)["train"]
    features = _eligible_features(train)
    rules: list[HypothesisRule] = []
    single_terms: list[RuleTerm] = []

    for feature in features:
        s = pd.to_numeric(train[feature], errors="coerce").dropna()
        if s.empty or s.nunique() < 20:
            continue
        for q in config.quantiles:
            threshold = float(s.quantile(q))
            op = "<=" if q < 0.5 else ">="
            term = RuleTerm(feature=feature, op=op, threshold=threshold)
            side = f"bottom {int(q * 100)}%" if q < 0.5 else f"top {int((1 - q) * 100)}%"
            rules.append(HypothesisRule(
                name=f"{feature}_{op}_{q:.2f}",
                terms=(term,),
                rationale=f"{feature} is in its training-sample {side}.",
            ))
            single_terms.append(term)

    pair_rules: list[HypothesisRule] = []
    price_terms = [t for t in single_terms if t.feature in PRICE_STATE_FEATURES]
    context_terms = [t for t in single_terms if t.feature in CONTEXT_FEATURES]
    for a in price_terms:
        for b in context_terms:
            if len(pair_rules) >= config.max_pair_rules:
                break
            pair_rules.append(HypothesisRule(
                name=f"{a.feature}_{a.op}_{a.threshold:.6g}__AND__{b.feature}_{b.op}_{b.threshold:.6g}",
                terms=(a, b),
                rationale=f"Interaction hypothesis: {a.feature} {a.op} {a.threshold:.4g} while {b.feature} {b.op} {b.threshold:.4g}.",
            ))
        if len(pair_rules) >= config.max_pair_rules:
            break

    return rules + pair_rules


def _forward_path_table(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Precompute the exact close-to-close return, MAE and MFE for every valid entry date."""
    n = len(frame)
    if horizon <= 0 or n <= horizon:
        return pd.DataFrame(columns=["forward_return", "mae", "mfe"])

    close = frame["close"].to_numpy(dtype=float)
    high = frame["high"].to_numpy(dtype=float)
    low = frame["low"].to_numpy(dtype=float)
    valid_n = n - horizon
    entry = close[:valid_n]
    end_close = close[horizon:horizon + valid_n]

    high_windows = np.lib.stride_tricks.sliding_window_view(high[1:], horizon)
    low_windows = np.lib.stride_tricks.sliding_window_view(low[1:], horizon)
    future_high = high_windows[:valid_n].max(axis=1)
    future_low = low_windows[:valid_n].min(axis=1)

    return pd.DataFrame(
        {
            "forward_return": end_close / entry - 1.0,
            "mae": future_low / entry - 1.0,
            "mfe": future_high / entry - 1.0,
        },
        index=frame.index[:valid_n],
    )


def _path_cache(frame: pd.DataFrame, horizons: Iterable[int]) -> dict[int, pd.DataFrame]:
    return {h: _forward_path_table(frame, h) for h in horizons}


def _baseline_cache(path_cache: dict[int, pd.DataFrame]) -> dict[int, dict]:
    return {h: summarize_forward_paths(paths) for h, paths in path_cache.items()}


def _evaluate_rule_on_frame(
    frame: pd.DataFrame,
    rule: HypothesisRule,
    paths: dict[int, pd.DataFrame],
    baseline: dict[int, dict],
    config: LabConfig,
) -> dict:
    mask = rule.mask(frame).reindex(frame.index).fillna(False)
    dates = frame.index[mask]
    result = {"name": rule.name, "rationale": rule.rationale, "entry_count": int(mask.sum()), "horizons": {}}
    for h in config.horizons:
        conditional = paths[h].loc[paths[h].index.intersection(dates)]
        cs = summarize_forward_paths(conditional)
        bs = baseline[h]
        if cs.get("n", 0) == 0 or bs.get("n", 0) == 0:
            continue
        result["horizons"][h] = {
            **cs,
            "normal_median_return": bs["median_return"],
            "median_excess_edge": float(cs["median_return"] - bs["median_return"]),
            "normal_win_probability": bs["win_probability"],
            "win_probability_edge": float(cs["win_probability"] - bs["win_probability"]),
            "sample_ok": bool(cs["n"] >= config.min_n),
        }
    return result


def evaluate_hypothesis(
    full_features: pd.DataFrame,
    rule: HypothesisRule,
    split: ResearchSplit = ResearchSplit(),
    config: LabConfig = LabConfig(),
    path_caches: dict[str, dict[int, pd.DataFrame]] | None = None,
    baselines: dict[str, dict[int, dict]] | None = None,
) -> dict:
    periods = split_periods(full_features, split)
    if path_caches is None:
        path_caches = {period: _path_cache(frame, config.horizons) for period, frame in periods.items()}
    if baselines is None:
        baselines = {period: _baseline_cache(path_caches[period]) for period in periods}
    out = {"name": rule.name, "rationale": rule.rationale, "terms": [asdict(t) for t in rule.terms], "periods": {}}
    for period, frame in periods.items():
        out["periods"][period] = _evaluate_rule_on_frame(frame, rule, path_caches[period], baselines[period], config)
    return out


def skeptic_verdict(result: dict, config: LabConfig = LabConfig()) -> dict:
    """Train performance alone can never pass this gate."""
    h = config.primary_horizon
    reasons: list[str] = []

    def metric(period: str) -> dict | None:
        return result.get("periods", {}).get(period, {}).get("horizons", {}).get(h)

    val = metric("validation")
    hold = metric("holdout")
    for name, block in (("validation", val), ("holdout", hold)):
        if not block:
            reasons.append(f"{name}: missing {h}d result")
            continue
        if block.get("n", 0) < config.min_n:
            reasons.append(f"{name}: sample {block.get('n', 0)} < {config.min_n}")

    if val:
        if val.get("median_excess_edge", -np.inf) <= config.min_validation_edge:
            reasons.append("validation: no positive median excess edge")
        if val.get("win_probability_edge", -np.inf) <= config.min_validation_win_edge:
            reasons.append("validation: no positive win-probability edge")
    if hold:
        if hold.get("median_excess_edge", -np.inf) <= config.min_holdout_edge:
            reasons.append("holdout: no positive median excess edge")
        if hold.get("win_probability_edge", -np.inf) <= config.min_holdout_win_edge:
            reasons.append("holdout: no positive win-probability edge")

    passed = not reasons
    score = None
    if passed and val and hold:
        score = float(
            min(val["median_excess_edge"], hold["median_excess_edge"])
            + 0.25 * min(val["win_probability_edge"], hold["win_probability_edge"])
        )
    return {"passed": passed, "score": score, "reasons": reasons}


def research_target(
    frames: dict[str, pd.DataFrame],
    target: str,
    split: ResearchSplit = ResearchSplit(),
    config: LabConfig = LabConfig(),
) -> dict:
    features = add_research_features(frames, target)
    periods = split_periods(features, split)
    rules = learn_hypotheses(features, split=split, config=config)

    screen_config = replace(config, horizons=(config.primary_horizon,))
    screen_paths = {period: _path_cache(frame, screen_config.horizons) for period, frame in periods.items()}
    screen_baselines = {period: _baseline_cache(screen_paths[period]) for period in periods}

    passed_rules: list[tuple[HypothesisRule, dict]] = []
    for rule in rules:
        screened = evaluate_hypothesis(
            features, rule, split=split, config=screen_config,
            path_caches=screen_paths, baselines=screen_baselines,
        )
        verdict = skeptic_verdict(screened, config=config)
        if verdict["passed"]:
            passed_rules.append((rule, verdict))

    survivors = []
    if passed_rules:
        full_paths = {period: _path_cache(frame, config.horizons) for period, frame in periods.items()}
        full_baselines = {period: _baseline_cache(full_paths[period]) for period in periods}
        for rule, verdict in passed_rules:
            result = evaluate_hypothesis(
                features, rule, split=split, config=config,
                path_caches=full_paths, baselines=full_baselines,
            )
            result["skeptic"] = verdict
            result["live_active"] = bool(rule.mask(features).iloc[-1])
            survivors.append(result)

    survivors.sort(key=lambda r: r["skeptic"]["score"] if r["skeptic"]["score"] is not None else -np.inf, reverse=True)
    live = [r for r in survivors if r.get("live_active")]

    return {
        "target": target.upper(),
        "as_of": str(pd.Timestamp(features.index.max()).date()),
        "candidate_count": len(rules),
        "survivor_count": len(survivors),
        "live_survivor_count": len(live),
        "survivors": survivors,
        "live": live,
    }


def run_autonomous_lab(
    frames: dict[str, pd.DataFrame],
    targets: Iterable[str] = ("SPY", "QQQ"),
    split: ResearchSplit = ResearchSplit(),
    config: LabConfig = LabConfig(),
) -> dict:
    """Run the isolated SPY/QQQ research lab without altering RE-ENTRY state or production files."""
    out = {"config": asdict(config), "targets": {}}
    for target in targets:
        target = target.upper()
        if target not in frames:
            raise KeyError(f"Missing target frame: {target}")
        out["targets"][target] = research_target(frames, target, split=split, config=config)
    return out
