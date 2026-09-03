from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_confidence import feature_frame, forward_return
from reentry_decision import decision_from_analogs

K_ANALOGS = 40
EXCLUSION_SESSIONS = 20
ROUND_TRIP_COST = 0.001
MIN_HISTORY = 252
PRIMARY_HORIZONS = (7, 10)
EPISODE_COOLDOWN = 10
FEATURES = ["spy_dd20", "spy_ret5", "B50", "B200", "b50_change1", "b50_change3", "vix_change5", "curve_ratio"]


def historical_analogs(frame: pd.DataFrame, pos: int) -> pd.DataFrame | None:
    cutoff = pos - EXCLUSION_SESSIONS
    if cutoff < MIN_HISTORY:
        return None
    hist = frame.iloc[:cutoff]
    target = frame.iloc[pos]
    # Reproduce the live engine's percentile normalization using only information
    # available at that historical date.
    combo = pd.concat([hist[FEATURES], target[FEATURES].to_frame().T])
    scaled = pd.DataFrame(index=combo.index)
    for c in FEATURES:
        scaled[c] = combo[c].rank(method="average", pct=True)
    target_scaled = scaled.iloc[-1]
    hist_scaled = scaled.iloc[:-1]
    dist = ((hist_scaled - target_scaled) ** 2).mean(axis=1) ** 0.5
    nearest = dist.nsmallest(min(K_ANALOGS, len(dist))).index
    result = hist.loc[nearest].copy()
    result["distance"] = dist.loc[nearest]
    return result.sort_values("distance")


def summarize_for_target(frame: pd.DataFrame, analogs: pd.DataFrame, current_pos: int) -> dict:
    output: dict[str, dict] = {}
    cutoff_date = frame.index[current_pos - EXCLUSION_SESSIONS]
    for symbol in ("SPY", "QQQ"):
        output[symbol] = {}
        for h in (5, 7, 10):
            fwd = forward_return(frame[symbol], h).reindex(analogs.index).dropna()
            unconditional = forward_return(frame[symbol], h).loc[:cutoff_date].dropna()
            med = float(fwd.median())
            base = float(unconditional.median())
            output[symbol][str(h)] = {
                "n": int(len(fwd)),
                "median_return": med,
                "positive_rate": float((fwd > 0).mean()),
                "unconditional_median": base,
                "median_excess": med - base,
                "p25": float(fwd.quantile(0.25)),
                "p75": float(fwd.quantile(0.75)),
            }
    return output


def generate_decisions(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pos in range(MIN_HISTORY + EXCLUSION_SESSIONS, len(frame) - 12):
        analogs = historical_analogs(frame, pos)
        if analogs is None or len(analogs) < K_ANALOGS:
            continue
        stats = summarize_for_target(frame, analogs, pos)
        row = frame.iloc[pos]
        decision, text, diagnostics = decision_from_analogs(stats, row)
        out = {
            "date": frame.index[pos],
            "decision": decision,
            "interpretation": text,
            **diagnostics,
            "spy_dd20": float(row["spy_dd20"]),
            "B50": float(row["B50"]),
            "B200": float(row["B200"]),
            "vix_change5": float(row["vix_change5"]),
            "curve_ratio": float(row["curve_ratio"]),
        }
        for symbol in ("SPY", "QQQ"):
            for h in PRIMARY_HORIZONS:
                fwd = forward_return(frame[symbol], h)
                out[f"{symbol}_{h}D"] = float(fwd.iloc[pos]) if pd.notna(fwd.iloc[pos]) else np.nan
        rows.append(out)
    return pd.DataFrame(rows).set_index("date")


def group_stats(df: pd.DataFrame, mask: pd.Series) -> dict:
    sub = df.loc[mask]
    result = {"n_days": int(len(sub))}
    for symbol in ("SPY", "QQQ"):
        for h in PRIMARY_HORIZONS:
            col = f"{symbol}_{h}D"
            x = sub[col].dropna()
            result[col] = {
                "n": int(len(x)),
                "median_return": float(x.median()) if len(x) else None,
                "mean_return": float(x.mean()) if len(x) else None,
                "positive_rate": float((x > 0).mean()) if len(x) else None,
                "p25": float(x.quantile(0.25)) if len(x) else None,
            }
    return result


def independent_episodes(df: pd.DataFrame) -> pd.DataFrame:
    positive = df["decision"].isin(["YES", "STRONG YES"])
    starts = positive & ~positive.shift(1, fill_value=False)
    keep = []
    last_pos = -10_000
    for i, flag in enumerate(starts.to_numpy()):
        if flag and i - last_pos > EPISODE_COOLDOWN:
            keep.append(i)
            last_pos = i
    return df.iloc[keep]


def bootstrap_difference(a: np.ndarray, b: np.ndarray, seed: int = 20260903, reps: int = 10000) -> dict:
    if len(a) < 5 or len(b) < 5:
        return {"median_diff": None, "ci_low": None, "ci_high": None, "p_one_sided": None}
    rng = np.random.default_rng(seed)
    diffs = np.empty(reps)
    for i in range(reps):
        sa = rng.choice(a, len(a), replace=True)
        sb = rng.choice(b, len(b), replace=True)
        diffs[i] = np.median(sa) - np.median(sb)
    observed = float(np.median(a) - np.median(b))
    return {
        "median_diff": observed,
        "ci_low": float(np.quantile(diffs, 0.025)),
        "ci_high": float(np.quantile(diffs, 0.975)),
        "p_one_sided": float((np.count_nonzero(diffs <= 0) + 1) / (reps + 1)),
    }


def main() -> None:
    frame = feature_frame()
    decisions = generate_decisions(frame)
    yes_mask = decisions["decision"].isin(["YES", "STRONG YES"])
    cautious_mask = decisions["decision"].eq("CAUTIOUS YES")
    no_mask = decisions["decision"].eq("NO")

    daily = {
        "YES_or_STRONG": group_stats(decisions, yes_mask),
        "CAUTIOUS_YES": group_stats(decisions, cautious_mask),
        "NO": group_stats(decisions, no_mask),
        "ALL": group_stats(decisions, pd.Series(True, index=decisions.index)),
    }

    episodes = independent_episodes(decisions)
    episode_stats = group_stats(episodes, pd.Series(True, index=episodes.index))

    comparisons = {}
    for symbol in ("SPY", "QQQ"):
        for h in PRIMARY_HORIZONS:
            col = f"{symbol}_{h}D"
            yes = decisions.loc[yes_mask, col].dropna().to_numpy(float)
            no = decisions.loc[no_mask, col].dropna().to_numpy(float)
            comparisons[col] = bootstrap_difference(yes, no, seed=20260903 + h + (1 if symbol == "QQQ" else 0))

    eras = {}
    for name, start, end in [("2017-2020", "2017-01-01", "2020-12-31"), ("2021-2026", "2021-01-01", "2026-12-31")]:
        sub = decisions.loc[(decisions.index >= start) & (decisions.index <= end)]
        eras[name] = {
            "YES_or_STRONG": group_stats(sub, sub["decision"].isin(["YES", "STRONG YES"])),
            "NO": group_stats(sub, sub["decision"].eq("NO")),
        }

    # Frozen validation gate: YES should be useful as a re-entry classifier, not merely positive.
    primary_checks = []
    for symbol in ("SPY", "QQQ"):
        for h in PRIMARY_HORIZONS:
            y = daily["YES_or_STRONG"][f"{symbol}_{h}D"]
            n = daily["NO"][f"{symbol}_{h}D"]
            c = comparisons[f"{symbol}_{h}D"]
            primary_checks.append(bool(
                y["n"] >= 30
                and n["n"] >= 30
                and y["median_return"] > n["median_return"]
                and y["positive_rate"] > n["positive_rate"]
                and c["median_diff"] is not None and c["median_diff"] > 0
            ))
    recent_good = True
    for symbol in ("SPY", "QQQ"):
        for h in PRIMARY_HORIZONS:
            y = eras["2021-2026"]["YES_or_STRONG"][f"{symbol}_{h}D"]
            recent_good = recent_good and y["n"] >= 20 and y["median_return"] is not None and y["median_return"] > 0 and y["positive_rate"] >= 0.55

    episode_good = episode_stats["n_days"] >= 20
    for symbol in ("SPY", "QQQ"):
        for h in PRIMARY_HORIZONS:
            e = episode_stats[f"{symbol}_{h}D"]
            episode_good = episode_good and e["median_return"] is not None and e["median_return"] > 0 and e["positive_rate"] >= 0.55

    verdict = "GO_TO_IMPLEMENTABLE_STRATEGY" if all(primary_checks) and recent_good and episode_good else "DO_NOT_PROMOTE"

    payload = {
        "verdict": verdict,
        "methodology": {
            "walk_forward": True,
            "decision_logic": "exact frozen reentry_decision.py thresholds",
            "historical_information_only": True,
            "analog_count": K_ANALOGS,
            "exclusion_sessions": EXCLUSION_SESSIONS,
            "min_history_sessions": MIN_HISTORY,
            "execution": "decision close t; hypothetical entry close t+1; 10 bps round-trip cost",
            "primary_horizons": list(PRIMARY_HORIZONS),
            "episode_definition": "transition into YES/STRONG YES with 10-session cooldown",
            "breadth_history_limitation": "true breadth begins 2016-09",
        },
        "date_range": [str(decisions.index.min().date()), str(decisions.index.max().date())],
        "decision_counts": {k: int(v) for k, v in decisions["decision"].value_counts().to_dict().items()},
        "daily_results": daily,
        "yes_vs_no_bootstrap": comparisons,
        "independent_reentry_episodes": {
            "dates": [str(x.date()) for x in episodes.index],
            "stats": episode_stats,
        },
        "eras": eras,
        "gate": {
            "all_primary_yes_beats_no": bool(all(primary_checks)),
            "recent_era_positive": bool(recent_good),
            "independent_episodes_positive": bool(episode_good),
        },
    }

    out = Path("artifacts/reentry_walkforward")
    out.mkdir(parents=True, exist_ok=True)
    (out / "reentry_walkforward_validation.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    decisions.to_csv(out / "reentry_walkforward_daily.csv")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
