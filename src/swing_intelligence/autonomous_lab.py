from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

import numpy as np
import pandas as pd

from .research import ResearchSplit, add_research_features, split_periods
from .tournament import SignalSpec, evaluate_signal


DEFAULT_HORIZONS = (1, 5, 10, 20, 30, 60, 120)

# Only stationary or relative features are eligible for autonomous threshold discovery.
# Raw prices and moving-average levels are intentionally excluded.
DISCOVERY_FEATURES = (
    "return_5d",
    "return_10d",
    "return_20d",
    "gap_sma_20",
    "gap_sma_50",
    "gap_sma_200",
    "sma20_slope_5d",
    "rsi_5",
    "rsi_14",
    "zscore_20",
    "drawdown_5d",
    "realized_vol_10",
    "realized_vol_20",
    "downside_vol_20",
    "atr_pct",
    "atr_pct_rank_252",
    "volume_z_20",
    "rsp_spy_ret_5d",
    "rsp_spy_ret_20d",
    "qqq_spy_ret_5d",
    "qqq_spy_ret_20d",
    "smh_qqq_ret_5d",
    "smh_qqq_ret_20d",
    "vix_ret_5d",
    "vix_ret_20d",
    "vix_z_20",
)

PRICE_STATE_FEATURES = {
    "return_5d",
    "return_10d",
    "return_20d",
    "gap_sma_20",
    "gap_sma_50",
    "gap_sma_200",
    "sma20_slope_5d",
    "rsi_5",
    "rsi_14",
    "zscore_20",
    "drawdown_5d",
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
    """Generate fixed hypotheses using training data only.

    Thresholds are learned strictly from the train partition, then frozen before
    validation/holdout evaluation. This prevents holdout-informed threshold selection.
    """
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

    # Autonomous interaction search is constrained to price-state x context pairs.
    # This captures combinations such as a pullback plus improving breadth/volatility
    # without creating an unbounded combinatorial search.
    pair_rules: list[HypothesisRule] = []
    price_terms = [t for t in single_terms if t.feature in PRICE_STATE_FEATURES]
    context_terms = [t for t in single_terms if t.feature in CONTEXT_FEATURES]
    for a in price_terms:
        for b in context_terms:
            if len(pair_rules) >= config.max_pair_rules:
                break
            name = f"{a.feature}_{a.op}_{a.threshold:.6g}__AND__{b.feature}_{b.op}_{b.threshold:.6g}"
            pair_rules.append(HypothesisRule(
                name=name,
                terms=(a, b),
                rationale=f"Interaction hypothesis: {a.feature} {a.op} {a.threshold:.4g} while {b.feature} {b.op} {b.threshold:.4g}.",
            ))
        if len(pair_rules) >= config.max_pair_rules:
            break

    return rules + pair_rules


def evaluate_hypothesis(
    full_features: pd.DataFrame,
    rule: HypothesisRule,
    split: ResearchSplit = ResearchSplit(),
    config: LabConfig = LabConfig(),
) -> dict:
    periods = split_periods(full_features, split)
    out = {"name": rule.name, "rationale": rule.rationale, "terms": [asdict(t) for t in rule.terms], "periods": {}}
    for period, frame in periods.items():
        spec = SignalSpec(rule.name, rule.mask(frame), rule.rationale)
        out["periods"][period] = evaluate_signal(frame, spec, horizons=config.horizons, min_n=config.min_n)
    return out


def skeptic_verdict(result: dict, config: LabConfig = LabConfig()) -> dict:
    """Apply a strict validation gate. Train performance alone can never pass."""
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
    rules = learn_hypotheses(features, split=split, config=config)
    survivors = []

    for rule in rules:
        result = evaluate_hypothesis(features, rule, split=split, config=config)
        verdict = skeptic_verdict(result, config=config)
        result["skeptic"] = verdict
        if verdict["passed"]:
            result["live_active"] = bool(rule.mask(features).iloc[-1])
            survivors.append(result)

    survivors.sort(key=lambda r: (r["skeptic"]["score"] is not None, r["skeptic"]["score"] or -np.inf), reverse=True)
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
    """Run the isolated SPY/QQQ research lab.

    This function does not alter RE-ENTRY state, signals, trades, or production files.
    It only returns research evidence.
    """
    out = {"config": asdict(config), "targets": {}}
    for target in targets:
        target = target.upper()
        if target not in frames:
            raise KeyError(f"Missing target frame: {target}")
        out["targets"][target] = research_target(frames, target, split=split, config=config)
    return out
