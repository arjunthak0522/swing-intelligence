from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd

from .autonomous_lab import (
    HypothesisRule,
    LabConfig,
    RuleTerm,
    evaluate_hypothesis,
    skeptic_verdict,
)
from .market_state_hypotheses import add_market_state_features, learn_market_state_hypotheses
from .research import ResearchSplit, add_research_features, split_periods


def _convert_rule(state_rule) -> HypothesisRule:
    return HypothesisRule(
        name=f"state__{state_rule.name}",
        terms=tuple(
            RuleTerm(feature=t.feature, op=t.op, threshold=t.threshold)
            for t in state_rule.terms
        ),
        rationale=f"[{state_rule.family}] {state_rule.rationale}",
    )


def build_semantic_features(frames: dict[str, pd.DataFrame], target: str) -> pd.DataFrame:
    return add_market_state_features(add_research_features(frames, target))


def learn_semantic_rules(
    features: pd.DataFrame,
    target: str,
    split: ResearchSplit = ResearchSplit(),
) -> list[HypothesisRule]:
    train = split_periods(features, split)["train"]
    return [_convert_rule(r) for r in learn_market_state_hypotheses(train, target)]


def research_semantic_target(
    frames: dict[str, pd.DataFrame],
    target: str,
    split: ResearchSplit = ResearchSplit(),
    config: LabConfig = LabConfig(),
) -> dict:
    """Evaluate predeclared semantic market-state hypotheses through the unchanged skeptic gate."""
    features = build_semantic_features(frames, target)
    rules = learn_semantic_rules(features, target, split=split)
    survivors = []
    rejected = []

    for rule in rules:
        result = evaluate_hypothesis(features, rule, split=split, config=config)
        verdict = skeptic_verdict(result, config=config)
        result["skeptic"] = verdict
        result["live_active"] = bool(rule.mask(features).iloc[-1])
        if verdict["passed"]:
            survivors.append(result)
        else:
            rejected.append({
                "name": result["name"],
                "rationale": result["rationale"],
                "reasons": verdict["reasons"],
            })

    survivors.sort(
        key=lambda r: r["skeptic"]["score"] if r["skeptic"]["score"] is not None else -np.inf,
        reverse=True,
    )
    live = [r for r in survivors if r.get("live_active")]
    return {
        "target": target.upper(),
        "as_of": str(pd.Timestamp(features.index.max()).date()),
        "candidate_count": len(rules),
        "survivor_count": len(survivors),
        "live_survivor_count": len(live),
        "survivors": survivors,
        "live": live,
        "rejected": rejected,
        "config": asdict(config),
    }


def run_semantic_lab(
    frames: dict[str, pd.DataFrame],
    targets=("SPY", "QQQ"),
    split: ResearchSplit = ResearchSplit(),
    config: LabConfig = LabConfig(),
) -> dict:
    return {
        "targets": {
            target.upper(): research_semantic_target(frames, target, split=split, config=config)
            for target in targets
        }
    }
