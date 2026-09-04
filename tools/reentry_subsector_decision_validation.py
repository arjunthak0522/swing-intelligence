from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from internal_correction_full_v2 import build_full_v2_state
from internal_correction_v2 import HORIZONS, PRIMARY_COOLDOWN, build_cross_section, cooldown_dates, forward_stats, load_prices
from reentry_confidence import analogs_for_date, feature_frame, summarize_analogs
from reentry_decision import decision_from_analogs
from reentry_early_entry_policy import early_entry_decision
from reentry_engine import _internal_reset, _selling_pressure, _unified_signal, weakness_context
from reentry_subsector_intelligence import build_subsector_frame, load_subsector_prices, subsector_snapshot
from reentry_subsector_decision import build_subsector_decision_evidence


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

    no_sub = []
    with_sub = []
    sub_sources = []

    for target in df.index:
        analogs = analogs_for_date(base, target)
        summary = summarize_analogs(base, analogs)
        analog_decision, _, _ = decision_from_analogs(summary, base.loc[target])
        row = df.loc[target]
        weak, _ = weakness_context(row)
        base_signal, _, _ = _unified_signal(analog_decision, weak, row)
        internal = _internal_reset(row)
        pressure = _selling_pressure(row)

        signal0, _, _ = early_entry_decision(
            analog_decision=analog_decision,
            weakness_present=weak,
            internal_reset=internal,
            selling_pressure=pressure,
            existing_signal=base_signal,
        )

        sub_snapshot = {"subsector_intelligence": subsector_snapshot(sub_frame.loc[target])}
        # Parent sector drawdowns are needed to identify hidden damage.
        sub_snapshot["signal_snapshot"] = {
            "sectors": {
                s: {"drawdown_20d": float(row[f"{s}_dd20"])}
                for s in ["XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLB", "XLRE", "XLK", "XLU"]
                if f"{s}_dd20" in row.index and pd.notna(row[f"{s}_dd20"])
            }
        }
        evidence = build_subsector_decision_evidence(sub_snapshot)
        signal1, _, source1 = early_entry_decision(
            analog_decision=analog_decision,
            weakness_present=weak,
            internal_reset=internal,
            selling_pressure=pressure,
            existing_signal=base_signal,
            subsector_state=str(evidence["state"]),
            subsector_supports_early_entry=bool(evidence["supports_early_entry"]),
        )
        no_sub.append(signal0)
        with_sub.append(signal1)
        sub_sources.append(source1)

    df["signal_without_subsector"] = no_sub
    df["signal_with_subsector"] = with_sub
    df["subsector_source"] = sub_sources
    df["incremental_subsector_reenter"] = (
        df["signal_with_subsector"].eq("RE-ENTER") & ~df["signal_without_subsector"].eq("RE-ENTER")
    )

    dates = cooldown_dates(df["incremental_subsector_reenter"], PRIMARY_COOLDOWN)
    payload = {
        "status": "RESEARCH_ONLY_SUBSECTOR_DECISION_VALIDATION",
        "sample_start": str(df.index.min().date()),
        "sample_end": str(df.index.max().date()),
        "incremental_subsector_events": len(dates),
        "decision_role": (
            "subsector repair may resolve a MIXED aggregate repair state when an internal reset and favorable analogs already exist"
        ),
        "SPY": {str(h): forward_stats(prices, dates, "SPY", h) for h in HORIZONS},
        "QQQ": {str(h): forward_stats(prices, dates, "QQQ", h) for h in HORIZONS},
        "era_counts": {
            "2016_2020": sum(d < pd.Timestamp("2021-01-01") for d in dates),
            "2021_present": sum(d >= pd.Timestamp("2021-01-01") for d in dates),
        },
        "latest_incremental_dates": [str(d.date()) for d in dates[-12:]],
    }

    out = Path("artifacts/internal_correction_v2/subsector_decision_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
