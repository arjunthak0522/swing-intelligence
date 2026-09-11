from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from reentry_confidence import analogs_for_date, empirical_state, feature_frame, summarize_analogs


def decision_from_analogs(stats: dict, current_row) -> tuple[str, str, dict]:
    # No minimum correction gate. Larger corrections remain fully eligible.
    cells = []
    for symbol in ("SPY", "QQQ"):
        for horizon in (7, 10):
            r = stats[symbol][str(horizon)]
            cells.append({
                "symbol": symbol,
                "horizon": horizon,
                "median_return": float(r["median_return"]),
                "positive_rate": float(r["positive_rate"]),
                "median_excess": float(r["median_excess"]),
                "p25": float(r["p25"]),
            })

    median_excess = float(np.median([c["median_excess"] for c in cells]))
    median_win = float(np.median([c["positive_rate"] for c in cells]))
    median_forward = float(np.median([c["median_return"] for c in cells]))
    worst_p25 = float(min(c["p25"] for c in cells))

    dd = float(current_row["spy_dd20"])
    b50 = float(current_row["B50"])
    b200 = float(current_row["B200"])
    b1 = float(current_row["b50_change1"])
    vix5 = float(current_row["vix_change5"])
    curve = float(current_row["curve_ratio"])

    # "Weakness present" can come from price, breadth, or volatility. It is not a hard
    # eligibility gate for the decision, but it helps distinguish a re-entry context
    # from simply chasing a fully extended market.
    weakness_present = bool(dd < 0 or b50 < 0.60 or b200 < 0.70 or vix5 > 0 or curve > 0.95)
    stabilizing = bool(b1 > 0 or vix5 <= 0 or curve <= 1.0)

    if median_forward <= 0 or median_win < 0.50:
        label = "NO"
        text = "historical analogs do not support deploying cash yet"
    elif median_excess > 0 and median_win >= 0.60 and stabilizing and weakness_present:
        if median_excess >= 0.005 and median_win >= 0.65 and worst_p25 > -0.02:
            label = "STRONG YES"
            text = "historical analogs strongly support putting cash back to work"
        else:
            label = "YES"
            text = "historical analogs support putting cash back to work"
    elif median_forward > 0 and median_win >= 0.55:
        label = "CAUTIOUS YES"
        text = "putting some cash back to work makes sense, but the edge is modest"
    else:
        label = "NO"
        text = "waiting still has better historical support"

    diagnostics = {
        "median_7_10d_excess_across_spy_qqq": median_excess,
        "median_7_10d_positive_rate_across_spy_qqq": median_win,
        "median_7_10d_forward_return_across_spy_qqq": median_forward,
        "worst_25th_percentile_across_spy_qqq": worst_p25,
        "weakness_present": weakness_present,
        "stabilizing": stabilizing,
    }
    return label, text, diagnostics


def main() -> None:
    frame = feature_frame()
    target = frame.index.max()
    analogs = analogs_for_date(frame, target)
    stats = summarize_analogs(frame, analogs)
    row = frame.loc[target]
    decision, interpretation, diagnostics = decision_from_analogs(stats, row)

    payload = {
        "as_of": str(target.date()),
        "question": "Does it make sense to put cash back into the market now?",
        "decision": decision,
        "interpretation": interpretation,
        "market_state": empirical_state(row),
        "current_inputs": {
            "spy_drawdown_20d": float(row["spy_dd20"]),
            "spy_return_5d": float(row["spy_ret5"]),
            "pct_sp500_above_50dma": float(row["B50"]),
            "pct_sp500_above_200dma": float(row["B200"]),
            "breadth_1d_change": float(row["b50_change1"]),
            "breadth_3d_change": float(row["b50_change3"]),
            "vix_5d_change": float(row["vix_change5"]),
            "vix_vix3m_ratio": float(row["curve_ratio"]),
        },
        "analog_count": int(len(analogs)),
        "closest_analog_dates": [str(d.date()) for d in analogs.index[:10]],
        "forward_outcomes": stats,
        "decision_diagnostics": diagnostics,
        "methodology": {
            "correction_depth_is_not_a_gate": True,
            "large_dips_included": True,
            "small_dips_included": True,
            "rolling_internal_corrections_included": True,
            "decision_basis": "40 nearest prior market-state analogs using price drawdown, true breadth, breadth change, VIX change and VIX/VIX3M; 7D and 10D SPY/QQQ outcomes summarized together",
            "execution_assumption": "signal close t, hypothetical entry close t+1, 10 bps round-trip cost",
            "caveat": "decision-support framework, not a claim of statistically proven standalone alpha; true breadth history begins 2016-09",
        },
    }

    out = Path("artifacts/reentry_confidence")
    out.mkdir(parents=True, exist_ok=True)
    (out / "reentry_decision.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
