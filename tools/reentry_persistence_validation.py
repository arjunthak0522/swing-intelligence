from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from internal_correction_full_v2 import build_full_v2_state
from internal_correction_v2 import build_cross_section, load_prices
from reentry_confidence import analogs_for_date, feature_frame, summarize_analogs
from reentry_decision import decision_from_analogs
from reentry_early_entry_policy import early_entry_decision
from reentry_engine import _internal_reset, _selling_pressure, _unified_signal, weakness_context

HORIZONS = (5, 10, 15, 30)
WINDOWS = range(0, 6)


def forward_return(series: pd.Series, loc: int, horizon: int) -> float | None:
    if loc + horizon >= len(series):
        return None
    start = float(series.iloc[loc])
    end = float(series.iloc[loc + horizon])
    if not np.isfinite(start) or not np.isfinite(end) or start <= 0:
        return None
    return end / start - 1.0


def forward_mae(series: pd.Series, loc: int, horizon: int) -> float | None:
    if loc + horizon >= len(series):
        return None
    start = float(series.iloc[loc])
    path = series.iloc[loc + 1 : loc + horizon + 1].astype(float)
    if start <= 0 or path.empty:
        return None
    return float((path / start - 1.0).min())


def main() -> None:
    base = feature_frame(require_same_day=False)
    prices = load_prices()
    xs = build_cross_section(prices)
    df = base.join(xs, how="inner").dropna(subset=["spy_dd20", "sector_dispersion_pct"]).copy()
    df = build_full_v2_state(df)

    qqq = prices["QQQ"].reindex(df.index)
    spy = prices["SPY"].reindex(df.index)

    intrinsic = []
    for target in df.index:
        try:
            analogs = analogs_for_date(base, target)
            stats = summarize_analogs(base, analogs)
            analog_decision, _, _ = decision_from_analogs(stats, base.loc[target])
        except Exception:
            intrinsic.append(False)
            continue
        row = df.loc[target]
        weak, _ = weakness_context(row)
        base_signal, _, _ = _unified_signal(analog_decision, weak, row)
        signal, _, _ = early_entry_decision(
            analog_decision=analog_decision,
            weakness_present=weak,
            internal_reset=_internal_reset(row),
            selling_pressure=_selling_pressure(row),
            existing_signal=base_signal,
        )
        intrinsic.append(signal == "RE-ENTER")

    intrinsic = pd.Series(intrinsic, index=df.index, dtype=bool)

    summary: dict[str, object] = {
        "status": "PERSISTENCE_RESEARCH_ONLY",
        "definition": "Persistence keeps RE-ENTER active for N sessions after an intrinsic RE-ENTER, unless a fresh intrinsic signal occurs. This validation measures the additional carried sessions, not the trigger sessions themselves.",
        "windows": {},
    }

    for window in WINDOWS:
        active = intrinsic.copy()
        if window > 0:
            last_trigger_loc = -10_000
            vals = []
            for i, is_trigger in enumerate(intrinsic.tolist()):
                if is_trigger:
                    last_trigger_loc = i
                    vals.append(True)
                else:
                    vals.append(i - last_trigger_loc <= window)
            active = pd.Series(vals, index=df.index, dtype=bool)

        carried = active & ~intrinsic
        cells = {
            "intrinsic_sessions": int(intrinsic.sum()),
            "active_sessions": int(active.sum()),
            "additional_carried_sessions": int(carried.sum()),
            "assets": {},
        }
        for symbol, series in (("SPY", spy), ("QQQ", qqq)):
            asset = {}
            for horizon in HORIZONS:
                rets = []
                maes = []
                for idx in np.flatnonzero(carried.values):
                    r = forward_return(series, idx, horizon)
                    m = forward_mae(series, idx, horizon)
                    if r is not None:
                        rets.append(r)
                    if m is not None:
                        maes.append(m)
                asset[str(horizon)] = {
                    "n": len(rets),
                    "median_return": float(np.median(rets)) if rets else None,
                    "positive_rate": float(np.mean(np.array(rets) > 0)) if rets else None,
                    "median_mae": float(np.median(maes)) if maes else None,
                    "bad_10d_rate": float(np.mean(np.array(rets) < -0.02)) if rets and horizon == 10 else None,
                }
            cells["assets"][symbol] = asset
        summary["windows"][str(window)] = cells

    out = Path("artifacts/reentry/persistence_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
