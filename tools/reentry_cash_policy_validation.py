from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_confidence import feature_frame
from reentry_walkforward_validation import generate_decisions

HORIZONS = (5, 10, 15, 30, 60)
FAVORABLE = {"CAUTIOUS YES", "YES", "STRONG YES"}
ROUND_TRIP_COST = 0.001
MAX_WAIT_TO_DEPLOY = 60


def historical_proxy_states(frame: pd.DataFrame, decisions: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct the consumer cash-policy states with only historically available inputs.

    IMPORTANT: this is intentionally a proxy for the new live market-condition layer.
    Exact historical SPXA20R/MMFD/NASI+/intraday fast-family series are not available
    across the validated history. The action/condition study therefore uses the frozen
    point-in-time S&P breadth, price drawdown and volatility inputs that powered the
    validated predecessor engine. It must not be represented as exact replication of
    today's intraday engine.
    """
    common = decisions.index.intersection(frame.index)
    d = decisions.loc[common].copy()
    f = frame.loc[common].copy()

    # Historical proxy for a genuinely stretched downside reset. This is narrower than
    # the broad predecessor weakness context and is deliberately based only on data that
    # existed point-in-time in the old validation set.
    oversold = (
        (f["B50"] <= 0.35)
        | (f["spy_dd20"] <= -0.04)
        | ((f["B50"] <= 0.45) & (f["vix_change5"] >= 0.10))
        | ((f["B50"] <= 0.45) & (f["curve_ratio"] >= 1.0))
    )

    favorable = d["decision"].isin(FAVORABLE)
    action = pd.Series("HOLD_CASH", index=common, dtype="object")
    action.loc[oversold] = "WATCH"
    action.loc[oversold & favorable] = "DEPLOY"

    extension_count = pd.DataFrame({
        "B50_STRONG": f["B50"] >= 0.70,
        "B200_STRONG": f["B200"] >= 0.75,
        "SPY_NEAR_20D_HIGH": f["spy_dd20"] >= -0.005,
        "VIX_EASING": f["vix_change5"] <= 0.0,
        "CURVE_CALM": f["curve_ratio"] <= 0.95,
    }, index=common).sum(axis=1)
    pullback_count = pd.DataFrame({
        "SPY_OFF_HIGH": f["spy_dd20"] <= -0.01,
        "B50_SOFT": f["B50"] < 0.60,
        "VIX_RISING": f["vix_change5"] > 0.0,
        "CURVE_FIRM": f["curve_ratio"] > 0.95,
    }, index=common).sum(axis=1)

    condition = pd.Series("BALANCED", index=common, dtype="object")
    condition.loc[(~oversold) & (extension_count >= 3)] = "EXTENDED"
    condition.loc[(~oversold) & (extension_count < 3) & (pullback_count >= 2)] = "PULLBACK"
    condition.loc[oversold] = "OVERSOLD"
    condition.loc[action == "DEPLOY"] = "RECOVERING_FROM_OVERSOLD"

    out = pd.DataFrame(index=common)
    out["analog_decision"] = d["decision"]
    out["deployment_signal"] = action
    out["market_condition"] = condition
    out["oversold_proxy"] = oversold.astype(bool)
    out["extension_signal_count_proxy"] = extension_count.astype(int)
    out["pullback_signal_count_proxy"] = pullback_count.astype(int)
    for c in ("SPY", "QQQ", "B50", "B200", "spy_dd20", "vix_change5", "curve_ratio"):
        out[c] = f[c]
    return out


def forward_return(price: pd.Series, horizon: int) -> pd.Series:
    # Signal known at close t; entry close t+1; exit after horizon sessions; 10 bps cost.
    return price.shift(-(horizon + 1)) / price.shift(-1) - 1.0 - ROUND_TRIP_COST


def path_stats(price: pd.Series, index: pd.Index, horizon: int) -> tuple[pd.Series, pd.Series]:
    mae = pd.Series(np.nan, index=index, dtype=float)
    mfe = pd.Series(np.nan, index=index, dtype=float)
    loc = {d: i for i, d in enumerate(price.index)}
    for d in index:
        i = loc.get(d)
        if i is None or i + 1 + horizon >= len(price):
            continue
        entry = float(price.iloc[i + 1])
        path = price.iloc[i + 1:i + 2 + horizon].astype(float)
        mae.at[d] = float(path.min() / entry - 1.0)
        mfe.at[d] = float(path.max() / entry - 1.0)
    return mae, mfe


def summarize(x: pd.Series) -> dict:
    x = pd.to_numeric(x, errors="coerce").dropna()
    if x.empty:
        return {"n": 0, "mean": None, "median": None, "positive_rate": None, "p25": None, "p75": None}
    return {
        "n": int(len(x)),
        "mean": float(x.mean()),
        "median": float(x.median()),
        "positive_rate": float((x > 0).mean()),
        "p25": float(x.quantile(0.25)),
        "p75": float(x.quantile(0.75)),
    }


def state_results(states: pd.DataFrame, frame: pd.DataFrame, column: str) -> dict:
    result: dict[str, dict] = {}
    labels = list(pd.unique(states[column]))
    for label in sorted(labels):
        mask = states[column].eq(label)
        block = {"n_days": int(mask.sum()), "SPY": {}, "QQQ": {}}
        for sym in ("SPY", "QQQ"):
            px = frame[sym].reindex(states.index)
            for h in HORIZONS:
                fwd = forward_return(px, h)
                mae, mfe = path_stats(px, states.index, h)
                block[sym][str(h)] = {
                    "forward": summarize(fwd.loc[mask]),
                    "max_adverse_excursion": summarize(mae.loc[mask]),
                    "max_favorable_excursion": summarize(mfe.loc[mask]),
                }
        result[label] = block
    return result


def transition_matrix(states: pd.DataFrame, column: str) -> dict:
    cur = states[column].astype(str)
    nxt = cur.shift(-1)
    counts = pd.crosstab(cur.iloc[:-1], nxt.iloc[:-1])
    out = {}
    for state in counts.index:
        total = int(counts.loc[state].sum())
        out[str(state)] = {
            str(dest): {"n": int(counts.at[state, dest]), "rate": float(counts.at[state, dest] / total)}
            for dest in counts.columns if counts.at[state, dest] > 0
        }
    return out


def wait_to_next_deploy(states: pd.DataFrame, frame: pd.DataFrame, source_state: str) -> dict:
    deploy_positions = np.flatnonzero(states["deployment_signal"].to_numpy() == "DEPLOY")
    source_positions = np.flatnonzero(states["deployment_signal"].to_numpy() == source_state)
    rows = []
    for pos in source_positions:
        later = deploy_positions[deploy_positions > pos]
        if not len(later):
            continue
        j = int(later[0])
        wait = j - pos
        if wait > MAX_WAIT_TO_DEPLOY or j + 1 >= len(states) or pos + 1 >= len(states):
            continue
        rec = {"wait_sessions": wait}
        for sym in ("SPY", "QQQ"):
            px = frame[sym].reindex(states.index)
            immediate = float(px.iloc[pos + 1])
            delayed = float(px.iloc[j + 1])
            # Positive means waiting bought at a lower price than immediate deployment.
            rec[f"{sym}_waiting_entry_advantage"] = immediate / delayed - 1.0
        rows.append(rec)
    if not rows:
        return {"n": 0}
    r = pd.DataFrame(rows)
    return {
        "n": int(len(r)),
        "median_wait_sessions": float(r["wait_sessions"].median()),
        "mean_wait_sessions": float(r["wait_sessions"].mean()),
        "SPY": summarize(r["SPY_waiting_entry_advantage"]),
        "QQQ": summarize(r["QQQ_waiting_entry_advantage"]),
        "interpretation": "positive waiting_entry_advantage means the next DEPLOY entry was cheaper than entering immediately; negative means waiting cost a higher entry price",
    }


def deploy_vs_wait(states: pd.DataFrame, frame: pd.DataFrame, wait: int) -> dict:
    mask = states["deployment_signal"].eq("DEPLOY")
    positions = np.flatnonzero(mask.to_numpy())
    result = {}
    for sym in ("SPY", "QQQ"):
        px = frame[sym].reindex(states.index)
        diffs = {str(h): [] for h in HORIZONS}
        for pos in positions:
            for h in HORIZONS:
                model_entry = pos + 1
                model_exit = model_entry + h
                wait_entry = pos + 1 + wait
                wait_exit = wait_entry + h
                if wait_exit >= len(px) or model_exit >= len(px):
                    continue
                model = float(px.iloc[model_exit] / px.iloc[model_entry] - 1.0 - ROUND_TRIP_COST)
                delayed = float(px.iloc[wait_exit] / px.iloc[wait_entry] - 1.0 - ROUND_TRIP_COST)
                diffs[str(h)].append(model - delayed)
        result[sym] = {h: summarize(pd.Series(vals, dtype=float)) for h, vals in diffs.items()}
    return result


def gate(actions: dict, conditions: dict, wait3: dict, wait5: dict) -> dict:
    checks = {}
    deploy = actions.get("DEPLOY", {})
    for sym in ("SPY", "QQQ"):
        for h in (10, 30, 60):
            cell = (((deploy.get(sym) or {}).get(str(h)) or {}).get("forward") or {})
            checks[f"DEPLOY_{sym}_{h}D_positive"] = bool(
                (cell.get("n") or 0) >= 25
                and (cell.get("median") is not None and cell["median"] > 0)
                and (cell.get("positive_rate") is not None and cell["positive_rate"] >= 0.55)
            )
    wait_advantage_checks = {}
    for wait_name, payload in (("wait3", wait3), ("wait5", wait5)):
        for sym in ("SPY", "QQQ"):
            for h in (10, 30):
                s = (((payload.get(sym) or {}).get(str(h))) or {})
                wait_advantage_checks[f"DEPLOY_vs_{wait_name}_{sym}_{h}D"] = bool(
                    (s.get("n") or 0) >= 25 and s.get("median") is not None and s["median"] > 0
                )
    deploy_supported = all(checks.values()) if checks else False
    timing_supported = sum(wait_advantage_checks.values()) >= max(1, len(wait_advantage_checks) // 2)
    return {
        "deploy_forward_quality_checks": checks,
        "deploy_beats_delayed_entry_checks": wait_advantage_checks,
        "deploy_supported": deploy_supported,
        "timing_supported": timing_supported,
        "overall_proxy_policy_verdict": "SUPPORTED" if deploy_supported and timing_supported else "NEEDS_REFINEMENT",
        "note": "This gate validates the historically reconstructable proxy policy. It does not certify exact live SPXA20R/MMFD/NASI+/intraday-family rules, which lack long historical reconstruction data.",
    }


def main() -> None:
    frame, metadata = feature_frame(return_metadata=True, require_same_day=False)
    decisions = generate_decisions(frame)
    states = historical_proxy_states(frame, decisions)
    aligned_frame = frame.reindex(states.index)

    actions = state_results(states, aligned_frame, "deployment_signal")
    conditions = state_results(states, aligned_frame, "market_condition")
    wait3 = deploy_vs_wait(states, aligned_frame, 3)
    wait5 = deploy_vs_wait(states, aligned_frame, 5)

    expected_actions = {"HOLD_CASH", "WATCH", "DEPLOY"}
    expected_conditions = {"EXTENDED", "BALANCED", "PULLBACK", "OVERSOLD", "RECOVERING_FROM_OVERSOLD"}
    observed_actions = set(actions)
    observed_conditions = set(conditions)

    payload = {
        "test_status": "COMPLETE" if expected_actions <= observed_actions and expected_conditions <= observed_conditions else "INCOMPLETE_STATE_COVERAGE",
        "question": "For an investor holding spare cash, do the HOLD CASH / WATCH / DEPLOY actions and descriptive market-condition regimes behave sensibly across historical market data?",
        "date_range": [str(states.index.min().date()), str(states.index.max().date())],
        "n_sessions": int(len(states)),
        "data_metadata": metadata,
        "methodology": {
            "historical_information_only": True,
            "no_lookahead_entry": "state at close t; hypothetical entry close t+1",
            "round_trip_cost": ROUND_TRIP_COST,
            "horizons": list(HORIZONS),
            "action_mapping": "historical proxy oversold gate + frozen walk-forward favorable analog decision => DEPLOY; proxy oversold without favorable analog => WATCH; otherwise HOLD_CASH",
            "condition_mapping": "RECOVERING_FROM_OVERSOLD on DEPLOY; OVERSOLD on proxy oversold without DEPLOY; otherwise EXTENDED/PULLBACK/BALANCED from point-in-time breadth, drawdown and volatility features",
            "exact_live_state_replication": False,
            "why_not_exact": "Long point-in-time history is unavailable for the current live SPXA20R, MMFD, NASI+, NYMO/NAMO, A/D-volume and intraday fast-family measurements. This study uses the validated historical feature set and explicitly does not invent those histories.",
        },
        "coverage": {
            "expected_actions": sorted(expected_actions),
            "observed_actions": sorted(observed_actions),
            "expected_conditions": sorted(expected_conditions),
            "observed_conditions": sorted(observed_conditions),
        },
        "action_results": actions,
        "condition_results": conditions,
        "action_transition_matrix": transition_matrix(states, "deployment_signal"),
        "condition_transition_matrix": transition_matrix(states, "market_condition"),
        "hold_to_next_deploy": wait_to_next_deploy(states, aligned_frame, "HOLD_CASH"),
        "watch_to_next_deploy": wait_to_next_deploy(states, aligned_frame, "WATCH"),
        "deploy_vs_wait_3_sessions": wait3,
        "deploy_vs_wait_5_sessions": wait5,
        "validation_gate": gate(actions, conditions, wait3, wait5),
    }

    out = Path("artifacts/reentry_cash_policy_validation")
    out.mkdir(parents=True, exist_ok=True)
    (out / "reentry_cash_policy_validation.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    states.to_csv(out / "reentry_cash_policy_daily_states.csv")

    compact = {
        "test_status": payload["test_status"],
        "date_range": payload["date_range"],
        "n_sessions": payload["n_sessions"],
        "coverage": payload["coverage"],
        "action_counts": {k: v["n_days"] for k, v in actions.items()},
        "condition_counts": {k: v["n_days"] for k, v in conditions.items()},
        "hold_to_next_deploy": payload["hold_to_next_deploy"],
        "watch_to_next_deploy": payload["watch_to_next_deploy"],
        "validation_gate": payload["validation_gate"],
    }
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
