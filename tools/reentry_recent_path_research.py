from __future__ import annotations

import json
from pathlib import Path

from internal_correction_full_v2 import build_full_v2_state
from internal_correction_v2 import build_cross_section, load_prices
from reentry_confidence import analogs_for_date, feature_frame, summarize_analogs
from reentry_decision import decision_from_analogs
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
        signal, signal_text, source = _unified_signal(analog_decision, weak, df.loc[target])
        row = df.loc[target]
        rows.append({
            "date": str(target.date()),
            "signal": signal,
            "signal_source": source,
            "analog_decision": analog_decision,
            "weakness_present": weak,
            "weakness_reasons": reasons,
            "internal_reset": _internal_reset(row),
            "stabilizing": bool(row["v2_stabilizing"]),
            "selling_pressure": _selling_pressure(row),
            "spy_dd20": float(row["spy_dd20"]),
            "spy_ret5": float(row["spy_ret5"]),
            "sector_damage_share_2": float(row["v2_sector_damage_share_2"]),
            "factor_damage_share_2": float(row["v2_factor_damage_share_2"]),
            "rotation_count": int(row["v2_rotation_count"]),
            "qqq_close": float(prices.loc[target, "QQQ"]) if target in prices.index else None,
            "spy_close": float(prices.loc[target, "SPY"]) if target in prices.index else None,
            "interpretation": signal_text,
            "analog_interpretation": analog_text,
        })

    out = {
        "status": "RECENT_PATH_RESEARCH_ONLY",
        "rows": rows,
    }
    path = Path("artifacts/internal_correction_v2/reentry_recent_path.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
