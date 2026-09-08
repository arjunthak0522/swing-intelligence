from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

FROZEN_TOOLS = Path("frozen/tools").resolve()
sys.path.insert(0, str(FROZEN_TOOLS))

from internal_correction_full_v2 import build_full_v2_state  # noqa: E402
from internal_correction_v2 import build_cross_section, load_prices  # noqa: E402
from reentry_confidence import analogs_for_date, feature_frame, summarize_analogs  # noqa: E402
from reentry_decision import decision_from_analogs  # noqa: E402
from reentry_engine import (  # noqa: E402
    _internal_reset,
    _market_damage,
    _selling_pressure,
    _unified_signal,
    early_entry_decision,
    weakness_context,
)

SNAPSHOT = Path("web/public/reentry/latest.json")
NUMERIC_TOLERANCE = 1e-6


def main() -> None:
    published = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    target = pd.Timestamp(published["as_of"]).normalize()

    base = feature_frame(require_same_day=False)
    if target not in base.index:
        raise RuntimeError(f"Published target {target.date()} missing from current core history")
    base = base.loc[:target].copy()

    prices = load_prices().loc[:target].copy()
    xs = build_cross_section(prices)
    frame = base.join(xs, how="inner").dropna(subset=["spy_dd20", "sector_dispersion_pct"]).copy()
    frame = build_full_v2_state(frame)
    if target not in frame.index:
        raise RuntimeError(f"Published target {target.date()} missing from rebuilt unified frame")
    row = frame.loc[target]

    analogs = analogs_for_date(base, target)
    decision_stats = summarize_analogs(base, analogs)
    analog_decision, analog_interpretation, _ = decision_from_analogs(decision_stats, row)
    weak, weak_reasons = weakness_context(row)
    base_signal, base_text, setup_source = _unified_signal(analog_decision, weak, row)
    final_signal, final_text, final_source = early_entry_decision(
        analog_decision=analog_decision,
        weakness_present=weak,
        internal_reset=_internal_reset(row),
        selling_pressure=_selling_pressure(row),
        existing_signal=base_signal,
        subsector_state="NEUTRAL",
        subsector_supports_early_entry=False,
        allow_subsector_candidate=False,
    )
    if final_signal == base_signal:
        final_text = base_text
        final_source = setup_source

    rebuilt_inputs = {
        "spy_drawdown_20d": float(row["spy_dd20"]),
        "spy_return_5d": float(row["spy_ret5"]),
        "pct_sp500_above_50dma": float(row["B50"]),
        "pct_sp500_above_200dma": float(row["B200"]),
        "breadth_1d_change": float(row["b50_change1"]),
        "breadth_3d_change": float(row["b50_change3"]),
        "vix_5d_change": float(row["vix_change5"]),
        "vix_vix3m_ratio": float(row["curve_ratio"]),
    }
    input_diffs = {}
    for key, value in rebuilt_inputs.items():
        old = float(published["current_inputs"][key])
        input_diffs[key] = {"published": old, "rebuilt": value, "abs_diff": abs(old - value)}

    categorical = {
        "signal": {"published": published["signal"], "rebuilt": final_signal},
        "analog_decision": {"published": published["analog_decision"], "rebuilt": analog_decision},
        "internal_reset": {"published": published["internal_reset"], "rebuilt": _internal_reset(row)},
        "selling_pressure": {"published": published["selling_pressure"], "rebuilt": _selling_pressure(row)},
        "market_damage": {"published": published["market_damage"], "rebuilt": _market_damage(row)},
        "weakness_present": {"published": bool(published["weakness_present"]), "rebuilt": bool(weak)},
    }
    categories_pass = all(x["published"] == x["rebuilt"] for x in categorical.values())
    inputs_pass = all(x["abs_diff"] <= NUMERIC_TOLERANCE for x in input_diffs.values())

    output = {
        "status": "PASS" if categories_pass and inputs_pass else "FAIL",
        "as_of": str(target.date()),
        "categorical_decision_comparison": categorical,
        "headline_input_comparison": input_diffs,
        "rebuilt_setup_source": final_source,
        "rebuilt_signal_interpretation": final_text,
        "rebuilt_analog_interpretation": analog_interpretation,
        "rebuilt_weakness_reasons": weak_reasons,
        "rebuilt_analog_count": int(len(analogs)),
        "rebuilt_closest_analog_dates": [str(d.date()) for d in analogs.index[:10]],
        "note": "This audit verifies the core published decision separately from the optional subsector outperformance layer. Sector/factor inputs are freshly fetched and therefore this test detects any decision-level drift caused by mutable external history.",
    }
    out = Path("artifacts/reentry_core_repro_audit")
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))
    if output["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
