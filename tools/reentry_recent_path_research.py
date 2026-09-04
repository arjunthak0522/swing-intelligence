from __future__ import annotations

import json
from pathlib import Path

from internal_correction_full_v2 import build_full_v2_state
from internal_correction_v2 import build_cross_section, load_prices
from reentry_confidence import analogs_for_date, feature_frame, summarize_analogs
from reentry_decision import decision_from_analogs
from reentry_early_entry_policy import early_entry_decision
from reentry_engine import _internal_reset, _selling_pressure, _unified_signal, weakness_context


def main() -> None:
    base = feature_frame(require_same_day=False)
    prices = load_prices()
    xs = build_cross_section(prices)
    df = base.join(xs, how="inner").dropna(subset=["spy_dd20", "sector_dispersion_pct"]).copy()
    df = build_full_v2_state(df)

    rows = []
    for target in df.index[-12:]:
        analogs = analogs_for_date(base, target)
        stats = summarize_analogs(base, analogs)
        analog_decision, analog_text, _ = decision_from_analogs(stats, base.loc[target])
        weak, reasons = weakness_context(df.loc[target])
        base_signal, base_text, base_source = _unified_signal(analog_decision, weak, df.loc[target])
        row = df.loc[target]
        internal_reset = _internal_reset(row)
        selling_pressure = _selling_pressure(row)
        early_signal, early_text, early_source = early_entry_decision(
            analog_decision=analog_decision,
            weakness_present=weak,
            internal_reset=internal_reset,
            selling_pressure=selling_pressure,
            existing_signal=base_signal,
        )
        rows.append({
            "date": str(target.date()),
            "base_signal": base_signal,
            "early_bias_signal": early_signal,
            "changed_by_early_bias": early_signal != base_signal,
            "base_signal_source": base_source,
            "early_signal_source": early_source,
            "analog_decision": analog_decision,
            "weakness_present": weak,
            "weakness_reasons": reasons,
            "internal_reset": internal_reset,
            "stabilizing": bool(row["v2_stabilizing"]),
            "selling_pressure": selling_pressure,
            "spy_dd20": float(row["spy_dd20"]),
            "spy_ret5": float(row["spy_ret5"]),
            "sector_damage_share_2": float(row["v2_sector_damage_share_2"]),
            "factor_damage_share_2": float(row["v2_factor_damage_share_2"]),
            "rotation_count": int(row["v2_rotation_count"]),
            "qqq_close": float(prices.loc[target, "QQQ"]) if target in prices.index else None,
            "spy_close": float(prices.loc[target, "SPY"]) if target in prices.index else None,
            "base_interpretation": base_text,
            "early_interpretation": early_text,
            "analog_interpretation": analog_text,
        })

    out = {
        "status": "RECENT_PATH_EARLY_ENTRY_RESEARCH_ONLY",
        "policy_preference": "slightly early rather than too late",
        "rows": rows,
    }
    path = Path("artifacts/internal_correction_v2/reentry_recent_path.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
