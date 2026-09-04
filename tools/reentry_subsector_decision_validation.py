from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from internal_correction_full_v2 import build_full_v2_state
from internal_correction_v2 import HORIZONS, PRIMARY_COOLDOWN, build_cross_section, cooldown_dates, load_prices
from reentry_confidence import analogs_for_date, feature_frame, summarize_analogs
from reentry_decision import decision_from_analogs
from reentry_early_entry_policy import early_entry_decision
from reentry_engine import _internal_reset, _selling_pressure, _unified_signal, weakness_context
from reentry_final_policy_validation import matched_validation, stats_for_dates, summarize_group
from reentry_subsector_intelligence import SUBSECTOR_GROUPS, build_subsector_frame, load_subsector_prices, subsector_snapshot
from reentry_subsector_decision import build_subsector_decision_evidence

DELAYS = (1, 2, 3, 5)
SECTORS = tuple(SUBSECTOR_GROUPS.keys())


def make_sub_snapshot(row: pd.Series, sub_row: pd.Series) -> dict:
    return {
        "subsector_intelligence": subsector_snapshot(sub_row),
        "signal_snapshot": {
            "sectors": {
                s: {"drawdown_20d": float(row[f"{s}_dd20"])}
                for s in SECTORS
                if f"{s}_dd20" in row.index and pd.notna(row[f"{s}_dd20"])
            }
        },
    }


def evidence_custom(
    snapshot: dict,
    *,
    damage_share: float = 0.50,
    repair_share: float = 0.25,
    parent_mild_dd: float = -0.03,
    excluded_sector: str | None = None,
) -> dict:
    by_sector = snapshot.get("subsector_intelligence", {}).get("by_sector", {})
    sectors = snapshot.get("signal_snapshot", {}).get("sectors", {})
    hidden, repairing, deep = [], [], []
    for parent, group in by_sector.items():
        if parent == excluded_sector:
            continue
        parent_dd = float(sectors.get(parent, {}).get("drawdown_20d", 0.0) or 0.0)
        damage3 = float(group.get("damage_share_3pct", 0.0) or 0.0)
        repair = float(group.get("repair_share", 0.0) or 0.0)
        if parent_dd > parent_mild_dd and damage3 >= damage_share:
            hidden.append(parent)
        if damage3 >= damage_share:
            deep.append(parent)
        if damage3 >= damage_share and repair >= repair_share:
            repairing.append(parent)
    hidden_any = bool(hidden)
    repair_any = bool(repairing)
    broad_hidden = len(hidden) >= 2
    broad_repair = len(repairing) >= 2
    if repair_any and hidden_any:
        state = "HIDDEN_DAMAGE_REPAIRING"
    elif broad_repair:
        state = "BROAD_REPAIR"
    elif repair_any:
        state = "REPAIRING"
    elif broad_hidden:
        state = "BROAD_HIDDEN_DAMAGE"
    elif hidden_any:
        state = "HIDDEN_DAMAGE"
    else:
        state = "NEUTRAL"
    return {
        "state": state,
        "supports_early_entry": state in {"HIDDEN_DAMAGE_REPAIRING", "BROAD_REPAIR", "REPAIRING"},
        "hidden_damage_sectors": hidden,
        "repairing_sectors": repairing,
        "deep_damage_sectors": deep,
    }


def signal_with_evidence(ctx: dict, evidence: dict) -> tuple[str, str]:
    signal, _, source = early_entry_decision(
        analog_decision=ctx["analog_decision"],
        weakness_present=ctx["weak"],
        internal_reset=ctx["internal"],
        selling_pressure=ctx["pressure"],
        existing_signal=ctx["base_signal"],
        subsector_state=str(evidence["state"]),
        subsector_supports_early_entry=bool(evidence["supports_early_entry"]),
    )
    return signal, source


def incremental_dates(df: pd.DataFrame, signals: list[str], baseline: list[str]) -> list[pd.Timestamp]:
    series = pd.Series(
        [a == "RE-ENTER" and b != "RE-ENTER" for a, b in zip(signals, baseline)],
        index=df.index,
        dtype=bool,
    )
    return cooldown_dates(series, PRIMARY_COOLDOWN)


def timing_comparison(prices: pd.DataFrame, dates: list[pd.Timestamp]) -> dict:
    out = {"SPY": {}, "QQQ": {}}
    for symbol in ("SPY", "QQQ"):
        s = prices[symbol].dropna()
        for h in HORIZONS:
            immediate = stats_for_dates(s, dates, h, 0)
            row = {"immediate": immediate}
            for delay in DELAYS:
                delayed = stats_for_dates(s, dates, h, delay)
                row[f"wait_{delay}d"] = delayed
                if immediate["median_return"] is not None and delayed["median_return"] is not None:
                    row[f"median_advantage_vs_wait_{delay}d"] = immediate["median_return"] - delayed["median_return"]
            out[symbol][str(h)] = row
    return out


def main() -> None:
    base = feature_frame(require_same_day=False)
    prices = load_prices()
    xs = build_cross_section(prices)
    df = base.join(xs, how="inner").dropna(subset=["spy_dd20", "sector_dispersion_pct"]).copy()
    df = build_full_v2_state(df)

    sub_prices = load_subsector_prices()
    sub_frame = build_subsector_frame(sub_prices)
    common = df.index.intersection(sub_frame.index)
    df = df.loc[common].copy()
    sub_frame = sub_frame.loc[common].copy()

    baseline_signals: list[str] = []
    final_signals: list[str] = []
    final_sources: list[str] = []
    contexts: dict[pd.Timestamp, dict] = {}
    support_counter: Counter[str] = Counter()

    for target in df.index:
        try:
            analogs = analogs_for_date(base, target)
            summary = summarize_analogs(base, analogs)
            analog_decision, _, _ = decision_from_analogs(summary, base.loc[target])
        except Exception:
            baseline_signals.append("NO RE-ENTRY SETUP")
            final_signals.append("NO RE-ENTRY SETUP")
            final_sources.append("UNAVAILABLE")
            continue

        row = df.loc[target]
        weak, _ = weakness_context(row)
        base_signal, _, _ = _unified_signal(analog_decision, weak, row)
        internal = _internal_reset(row)
        pressure = _selling_pressure(row)
        baseline, _, _ = early_entry_decision(
            analog_decision=analog_decision,
            weakness_present=weak,
            internal_reset=internal,
            selling_pressure=pressure,
            existing_signal=base_signal,
        )
        snap = make_sub_snapshot(row, sub_frame.loc[target])
        evidence = build_subsector_decision_evidence(snap)
        ctx = {
            "analog_decision": analog_decision,
            "weak": weak,
            "internal": internal,
            "pressure": pressure,
            "base_signal": base_signal,
            "snapshot": snap,
        }
        signal, source = signal_with_evidence(ctx, evidence)
        contexts[target] = ctx
        baseline_signals.append(baseline)
        final_signals.append(signal)
        final_sources.append(source)
        if signal == "RE-ENTER" and baseline != "RE-ENTER":
            support_counter.update(evidence.get("repairing_sectors", []))

    # Keep lists aligned if an early-history analog exception occurred.
    if len(baseline_signals) != len(df.index):
        raise RuntimeError("signal alignment failure")

    df["signal_without_subsector"] = baseline_signals
    df["signal_with_subsector"] = final_signals
    df["subsector_source"] = final_sources
    df["broad_weakness"] = [contexts.get(d, {}).get("weak", False) for d in df.index]
    df["incremental_subsector_reenter"] = (
        df["signal_with_subsector"].eq("RE-ENTER") & ~df["signal_without_subsector"].eq("RE-ENTER")
    )
    dates = cooldown_dates(df["incremental_subsector_reenter"], PRIMARY_COOLDOWN)

    eras = {
        "2016_2020": [d for d in dates if d < pd.Timestamp("2021-01-01")],
        "2021_present": [d for d in dates if d >= pd.Timestamp("2021-01-01")],
    }

    # Leave-one-parent-sector-out: no single parent sector should create the whole result.
    leave_one_out = {}
    for excluded in SECTORS:
        signals = []
        base_for_dates = []
        idx = []
        for d in df.index:
            ctx = contexts.get(d)
            if ctx is None:
                continue
            ev = evidence_custom(ctx["snapshot"], excluded_sector=excluded)
            sig, _ = signal_with_evidence(ctx, ev)
            signals.append(sig)
            base_for_dates.append(str(df.loc[d, "signal_without_subsector"]))
            idx.append(d)
        temp = df.loc[idx]
        ds = incremental_dates(temp, signals, base_for_dates)
        leave_one_out[excluded] = {
            "event_count": len(ds),
            "SPY_10D": stats_for_dates(prices["SPY"].dropna(), ds, 10),
            "SPY_30D": stats_for_dates(prices["SPY"].dropna(), ds, 30),
            "QQQ_10D": stats_for_dates(prices["QQQ"].dropna(), ds, 10),
            "QQQ_30D": stats_for_dates(prices["QQQ"].dropna(), ds, 30),
        }

    # Neighboring definitions only: robustness, not optimization.
    threshold_robustness = {}
    for damage_share in (0.40, 0.50, 0.60):
        for repair_share in (0.20, 0.25, 0.33):
            key = f"damage_{damage_share:.2f}_repair_{repair_share:.2f}"
            signals, baseline, idx = [], [], []
            for d in df.index:
                ctx = contexts.get(d)
                if ctx is None:
                    continue
                ev = evidence_custom(
                    ctx["snapshot"], damage_share=damage_share, repair_share=repair_share
                )
                sig, _ = signal_with_evidence(ctx, ev)
                signals.append(sig)
                baseline.append(str(df.loc[d, "signal_without_subsector"]))
                idx.append(d)
            ds = incremental_dates(df.loc[idx], signals, baseline)
            threshold_robustness[key] = {
                "event_count": len(ds),
                "SPY_10D_median": stats_for_dates(prices["SPY"].dropna(), ds, 10)["median_return"],
                "SPY_30D_median": stats_for_dates(prices["SPY"].dropna(), ds, 30)["median_return"],
                "QQQ_10D_median": stats_for_dates(prices["QQQ"].dropna(), ds, 10)["median_return"],
                "QQQ_30D_median": stats_for_dates(prices["QQQ"].dropna(), ds, 30)["median_return"],
            }

    payload = {
        "status": "FINAL_SUBSECTOR_DECISION_RESEARCH_ONLY",
        "sample_start": str(df.index.min().date()),
        "sample_end": str(df.index.max().date()),
        "incremental_subsector_events": len(dates),
        "decision_role": (
            "subsector repair may resolve a MIXED aggregate repair state when an internal reset and favorable analogs already exist; it is not a standalone trigger or veto"
        ),
        "execution": "next trading-session close; stats_for_dates includes 10 bps round-trip friction",
        "incremental_outcomes": summarize_group(prices, dates),
        "immediate_vs_wait": timing_comparison(prices, dates),
        "matched_controls": matched_validation(df, prices, dates, "incremental_subsector_reenter"),
        "era_split": {name: summarize_group(prices, ds) for name, ds in eras.items()},
        "supporting_parent_sector_counts": dict(support_counter.most_common()),
        "leave_one_parent_sector_out": leave_one_out,
        "neighbor_threshold_robustness": threshold_robustness,
        "latest_incremental_dates": [str(d.date()) for d in dates[-12:]],
        "limitations": [
            "ETF subsector proxies are not proprietary point-in-time industry constituent histories.",
            "Matched controls are diagnostic and do not establish causal identification.",
            "Neighbor-threshold tests are robustness checks only and must not be used to cherry-pick a new threshold.",
        ],
    }

    out = Path("artifacts/internal_correction_v2/subsector_decision_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
