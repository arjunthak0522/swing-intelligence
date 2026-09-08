from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CANONICAL_ENGINE_COMMIT = "47f38bf3362a97bcf9c9dd2d6545c4fae212e046"
CANONICAL_FINAL_POLICY_COUNT = 193
CANONICAL_FORWARD_MEDIANS = {
    "SPY": {5: 0.001869905317, 10: 0.012231318839, 30: 0.029441430001, 60: 0.045649433931},
    "QQQ": {5: 0.004700402611, 10: 0.016499431066, 30: 0.033520727249, 60: 0.059757936338},
}
ROUND_TRIP_COST = 0.001


def summarize(values: list[float]) -> dict[str, Any]:
    a = np.asarray(values, dtype=float)
    if len(a) == 0:
        return {"n": 0, "median": None, "mean": None, "positive_rate": None, "p25": None, "p75": None, "min": None, "max": None}
    return {
        "n": int(len(a)), "median": float(np.median(a)), "mean": float(np.mean(a)),
        "positive_rate": float(np.mean(a > 0)), "p25": float(np.quantile(a, 0.25)),
        "p75": float(np.quantile(a, 0.75)), "min": float(np.min(a)), "max": float(np.max(a)),
    }


def forward_return(series: pd.Series, date: pd.Timestamp, horizon: int) -> float | None:
    if date not in series.index:
        return None
    loc = series.index.get_loc(date)
    if not isinstance(loc, (int, np.integer)):
        return None
    entry_loc = loc + 1
    end_loc = entry_loc + horizon
    if end_loc >= len(series):
        return None
    entry = float(series.iloc[entry_loc])
    end = float(series.iloc[end_loc])
    return end / entry - 1.0 - ROUND_TRIP_COST


def build_exact_policy(canonical_tools: Path):
    sys.path.insert(0, str(canonical_tools))
    from internal_correction_full_v2 import build_full_v2_state  # type: ignore
    from internal_correction_v2 import build_cross_section, cooldown_dates, load_prices, PRIMARY_COOLDOWN  # type: ignore
    from reentry_confidence import analogs_for_date, feature_frame, summarize_analogs  # type: ignore
    from reentry_decision import decision_from_analogs  # type: ignore
    from reentry_early_entry_policy import early_entry_decision  # type: ignore
    from reentry_engine import _internal_reset, _selling_pressure, _unified_signal, weakness_context  # type: ignore

    base = feature_frame(require_same_day=False)
    prices = load_prices()
    xs = build_cross_section(prices)
    df = base.join(xs, how="inner").dropna(subset=["spy_dd20", "sector_dispersion_pct"]).copy()
    df = build_full_v2_state(df)

    final_signal, source, analog_labels = [], [], []
    for target in df.index:
        try:
            analogs = analogs_for_date(base, target)
            analog_summary = summarize_analogs(base, analogs)
            analog_decision, _, _ = decision_from_analogs(analog_summary, base.loc[target])
        except Exception:
            final_signal.append("NO RE-ENTRY SETUP"); source.append("UNAVAILABLE"); analog_labels.append("NO")
            continue
        row = df.loc[target]
        weak, _ = weakness_context(row)
        base_signal, _, _ = _unified_signal(analog_decision, weak, row)
        signal, _, signal_source = early_entry_decision(
            analog_decision=analog_decision, weakness_present=weak,
            internal_reset=_internal_reset(row), selling_pressure=_selling_pressure(row), existing_signal=base_signal,
        )
        final_signal.append(signal); source.append(signal_source); analog_labels.append(analog_decision)

    df["final_signal"] = final_signal
    df["signal_source"] = source
    df["analog_decision"] = analog_labels
    df["final_reenter"] = df["final_signal"].eq("RE-ENTER")
    signal_dates = cooldown_dates(df["final_reenter"], PRIMARY_COOLDOWN)
    return prices, df, signal_dates, PRIMARY_COOLDOWN


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-root", default="canonical")
    parser.add_argument("--output", default="web/public/reentry/historical_episodes.json")
    args = parser.parse_args()
    canonical_tools = Path(args.canonical_root).resolve() / "tools"
    if not canonical_tools.exists():
        raise SystemExit(f"Canonical tools path not found: {canonical_tools}")

    prices, df, signal_dates, cooldown = build_exact_policy(canonical_tools)
    if len(signal_dates) != CANONICAL_FINAL_POLICY_COUNT:
        raise RuntimeError(f"Exact final-policy count drifted: rebuilt={len(signal_dates)} archived={CANONICAL_FINAL_POLICY_COUNT}. Historical rows are not safe to publish.")

    rebuilt_forward: dict[str, dict[str, float | None]] = {"SPY": {}, "QQQ": {}}
    tolerance = 0.00075
    for sym in ("SPY", "QQQ"):
        series = prices[sym].dropna()
        for h in (5, 10, 30, 60):
            vals = [x for d in signal_dates if (x := forward_return(series, d, h)) is not None]
            median = float(np.median(vals)) if vals else None
            rebuilt_forward[sym][f"{h}D_median"] = median
            expected = CANONICAL_FORWARD_MEDIANS[sym][h]
            if median is None or abs(median - expected) > tolerance:
                raise RuntimeError(f"Final-policy forward median drifted for {sym} {h}D: rebuilt={median} archived={expected}. Historical rows are not safe to publish.")

    idx = list(df.index)
    pos = {d: i for i, d in enumerate(idx)}
    rows: list[dict[str, Any]] = []
    for signal_date in signal_dates:
        start_i = pos[signal_date]
        last_i = start_i
        while last_i + 1 < len(idx) and str(df.iloc[last_i + 1]["final_signal"]) == "RE-ENTER":
            last_i += 1
        last_date = idx[last_i]
        next_i = last_i + 1 if last_i + 1 < len(idx) else None
        next_date = idx[next_i] if next_i is not None else None
        next_signal = str(df.iloc[next_i]["final_signal"]) if next_i is not None else None
        rec: dict[str, Any] = {
            "start": str(pd.Timestamp(signal_date).date()), "last_favorable": str(pd.Timestamp(last_date).date()),
            "next_state_date": str(pd.Timestamp(next_date).date()) if next_date is not None else None,
            "next_state": next_signal, "active_at_sample_end": next_i is None,
            "reenter_sessions": int(last_i - start_i + 1), "setup_source": str(df.loc[signal_date, "signal_source"]),
            "analog_at_start": str(df.loc[signal_date, "analog_decision"]),
        }
        for sym in ("SPY", "QQQ"):
            series = prices[sym].dropna()
            if signal_date not in series.index or last_date not in series.index:
                raise RuntimeError(f"Missing {sym} price for {signal_date} to {last_date}")
            entry, last = float(series.loc[signal_date]), float(series.loc[last_date])
            p0, p1 = series.index.get_loc(signal_date), series.index.get_loc(last_date)
            if not isinstance(p0, (int, np.integer)) or not isinstance(p1, (int, np.integer)):
                raise RuntimeError("Unexpected duplicate price index")
            path = series.iloc[p0:p1 + 1].astype(float)
            rec[f"{sym}_entry_close"] = entry
            rec[f"{sym}_last_favorable_close"] = last
            rec[f"{sym}_return_during_episode"] = last / entry - 1.0
            rec[f"{sym}_max_gain_during_episode"] = float(path.max() / entry - 1.0)
            rec[f"{sym}_max_adverse_during_episode"] = float(path.min() / entry - 1.0)
        rows.append(rec)

    completed = [r for r in rows if not r["active_at_sample_end"]]
    summary = {
        "completed_episode_count": len(completed), "active_at_sample_end_count": len(rows) - len(completed),
        "episode_length_sessions": summarize([float(r["reenter_sessions"]) for r in completed]),
        "SPY": {"return_during_episode": summarize([float(r["SPY_return_during_episode"]) for r in completed]), "max_gain_during_episode": summarize([float(r["SPY_max_gain_during_episode"]) for r in completed]), "max_adverse_during_episode": summarize([float(r["SPY_max_adverse_during_episode"]) for r in completed])},
        "QQQ": {"return_during_episode": summarize([float(r["QQQ_return_during_episode"]) for r in completed]), "max_gain_during_episode": summarize([float(r["QQQ_max_gain_during_episode"]) for r in completed]), "max_adverse_during_episode": summarize([float(r["QQQ_max_adverse_during_episode"]) for r in completed])},
    }
    payload = {
        "schema_version": "2.0", "canonical_engine_commit": CANONICAL_ENGINE_COMMIT,
        "validated_independent_reentry_signals": CANONICAL_FINAL_POLICY_COUNT, "reconstructed_signal_rows": len(rows),
        "signal_selection_definition": f"Exact canonical final policy with the validated {cooldown}-session cooldown, reproducing the archived final-policy validation population.",
        "definition": "For each validated RE-ENTRY signal event, performance is measured from that completed signal close through the last consecutive completed close that still says RE-ENTER. The following WAIT or NO RE-ENTRY SETUP close is reported separately and is not included in the episode return.",
        "return_definition": "last favorable close divided by signal close minus one; historical measurement only, not an exit or sell rule",
        "summary_completed_episodes": summary, "fixed_horizon_validation": rebuilt_forward, "episodes": list(reversed(rows)),
    }
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"validated_final_policy_signals": len(rows), "completed": len(completed), "active_at_sample_end": len(rows)-len(completed), "SPY_episode_median": summary["SPY"]["return_during_episode"]["median"], "SPY_episode_positive_rate": summary["SPY"]["return_during_episode"]["positive_rate"], "QQQ_episode_median": summary["QQQ"]["return_during_episode"]["median"], "QQQ_episode_positive_rate": summary["QQQ"]["return_during_episode"]["positive_rate"], "median_sessions": summary["episode_length_sessions"]["median"], "forward_reconciliation": rebuilt_forward, "output": str(out)}, indent=2))


if __name__ == "__main__":
    main()
