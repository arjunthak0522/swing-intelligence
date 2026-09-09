from __future__ import annotations

from dataclasses import dataclass, asdict

import pandas as pd

from .autonomous_lab import HypothesisRule, RuleTerm, _forward_path_table
from .outcomes import summarize_forward_paths
from .robustness import block_bootstrap_edge, benjamini_hochberg


@dataclass(frozen=True)
class RobustnessConfig:
    horizon: int = 30
    min_event_gap: int = 30
    min_independent_events: int = 8
    bootstrap_iterations: int = 1000
    bootstrap_block: int = 3
    fdr_alpha: float = 0.10


def rule_from_result(result: dict) -> HypothesisRule:
    terms = tuple(
        RuleTerm(
            feature=str(term["feature"]),
            op=str(term["op"]),
            threshold=float(term["threshold"]),
        )
        for term in result.get("terms", [])
    )
    if not terms:
        raise ValueError("Result does not contain reconstructable rule terms")
    return HypothesisRule(
        name=str(result["name"]),
        terms=terms,
        rationale=str(result.get("rationale", "")),
    )


def independent_event_dates(frame: pd.DataFrame, mask: pd.Series, min_gap: int = 30) -> list[pd.Timestamp]:
    """Collapse clustered matches into independent episodes separated by trading rows."""
    aligned = mask.reindex(frame.index).fillna(False).astype(bool)
    positions = [i for i, flag in enumerate(aligned.to_numpy()) if flag]
    selected: list[int] = []
    last = None
    for pos in positions:
        if last is None or pos - last >= min_gap:
            selected.append(pos)
            last = pos
    return [pd.Timestamp(frame.index[i]) for i in selected]


def evaluate_independent_rule(
    frame: pd.DataFrame,
    rule: HypothesisRule,
    config: RobustnessConfig = RobustnessConfig(),
) -> dict:
    paths = _forward_path_table(frame, config.horizon)
    baseline = summarize_forward_paths(paths)
    dates = independent_event_dates(frame, rule.mask(frame), min_gap=config.min_event_gap)
    conditional = paths.loc[paths.index.intersection(dates)]
    stats = summarize_forward_paths(conditional)

    out = {
        "name": rule.name,
        "independent_events": int(stats.get("n", 0)),
        "median_return": stats.get("median_return"),
        "win_probability": stats.get("win_probability"),
        "median_excess_edge": None,
        "win_probability_edge": None,
        "bootstrap_p_value": None,
        "bootstrap_ci_low": None,
        "bootstrap_ci_high": None,
    }
    if stats.get("n", 0):
        out["median_excess_edge"] = float(stats["median_return"] - baseline["median_return"])
        out["win_probability_edge"] = float(stats["win_probability"] - baseline["win_probability"])

    if stats.get("n", 0) >= config.min_independent_events and baseline.get("n", 0) >= 100:
        boot = block_bootstrap_edge(
            conditional["forward_return"],
            paths["forward_return"],
            iterations=config.bootstrap_iterations,
            block=config.bootstrap_block,
            seed=7,
        )
        out["bootstrap_p_value"] = boot.p_value_one_sided
        out["bootstrap_ci_low"] = boot.ci_low
        out["bootstrap_ci_high"] = boot.ci_high

    return out


def robustness_report(
    frame: pd.DataFrame,
    survivor_results: list[dict],
    config: RobustnessConfig = RobustnessConfig(),
) -> dict:
    """Re-test first-pass survivors using episode-level evidence and FDR control."""
    rows = []
    p_values: dict[str, float] = {}
    for result in survivor_results:
        rule = rule_from_result(result)
        row = evaluate_independent_rule(frame, rule, config=config)
        rows.append(row)
        if row["bootstrap_p_value"] is not None:
            p_values[row["name"]] = float(row["bootstrap_p_value"])

    fdr = benjamini_hochberg(p_values, alpha=config.fdr_alpha)
    fdr_map = {}
    if not fdr.empty:
        fdr_map = {str(r.signal): bool(r.passes_fdr) for r in fdr.itertuples(index=False)}

    for row in rows:
        row["passes_fdr"] = fdr_map.get(row["name"], False)
        row["robust"] = bool(
            row["independent_events"] >= config.min_independent_events
            and row["median_excess_edge"] is not None
            and row["median_excess_edge"] > 0
            and row["win_probability_edge"] is not None
            and row["win_probability_edge"] > 0
            and row["bootstrap_ci_low"] is not None
            and row["bootstrap_ci_low"] > 0
            and row["passes_fdr"]
        )

    rows.sort(
        key=lambda r: (
            r["robust"],
            r["median_excess_edge"] if r["median_excess_edge"] is not None else -999.0,
        ),
        reverse=True,
    )
    return {
        "config": asdict(config),
        "tested": len(rows),
        "robust_count": sum(1 for row in rows if row["robust"]),
        "rows": rows,
    }
