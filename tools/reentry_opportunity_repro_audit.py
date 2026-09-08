from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

FROZEN_TOOLS = Path("frozen/tools").resolve()
sys.path.insert(0, str(FROZEN_TOOLS))

from reentry_confidence import feature_frame  # noqa: E402
from reentry_episode_exit_backtest import build_canonical_signal_history  # noqa: E402
from reentry_conditional_outperform_backtest import (  # noqa: E402
    K,
    PRED_H,
    episode_starts,
    independent,
    fret,
    frow,
    predict_for_symbol,
)
from reentry_subsector_intelligence import build_subsector_frame, load_subsector_prices  # noqa: E402

SNAPSHOT = Path("web/public/reentry/latest.json")
TOLERANCE = 1e-8


def reconstruct(px: pd.DataFrame, sf: pd.DataFrame, dates: list[pd.Timestamp], as_of: pd.Timestamp, sym: str) -> dict:
    current = frow(sf, as_of, sym)
    if current is None:
        raise RuntimeError(f"Current feature row unavailable for {sym}")

    history = []
    for d in dates:
        vector = frow(sf, d, sym)
        if vector is None:
            continue
        horizon_excess = []
        valid = True
        for h in PRED_H:
            asset_return = fret(px, d, sym, h)
            spy_return = fret(px, d, "SPY", h)
            if asset_return is None or spy_return is None:
                valid = False
                break
            horizon_excess.append(float(asset_return - spy_return))
        if valid:
            history.append((d, vector, float(np.mean(horizon_excess)), horizon_excess))

    if len(history) < 20:
        raise RuntimeError(f"Insufficient prior history for {sym}: {len(history)}")

    X = np.vstack([row[1] for row in history])
    mu = X.mean(0)
    sd = X.std(0)
    sd[sd == 0] = 1
    normalized_hist = (X - mu) / sd
    normalized_current = (current - mu) / sd
    distances = np.sqrt(((normalized_hist - normalized_current) ** 2).mean(axis=1))
    selected = np.argsort(distances)[: min(K, len(history))]

    neighbors = []
    targets = []
    for idx in selected:
        d, _, target, horizon_excess = history[int(idx)]
        targets.append(target)
        neighbors.append({
            "date": str(d.date()),
            "distance": float(distances[int(idx)]),
            "excess_10d_vs_spy": float(horizon_excess[0]),
            "excess_30d_vs_spy": float(horizon_excess[1]),
            "average_10d_30d_excess_vs_spy": float(target),
        })

    return {
        "reconstructed_score": float(np.median(np.asarray(targets))),
        "reconstructed_positive_rate": float(np.mean(np.asarray(targets) > 0)),
        "neighbors": neighbors,
    }


def main() -> None:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    as_of = pd.Timestamp(snapshot["as_of"]).tz_localize(None).normalize()
    published = snapshot.get("outperformance_intelligence", {}).get("candidates", [])
    if not published:
        raise RuntimeError("No published outperformance candidates to audit")

    base = feature_frame(require_same_day=False)
    signals = build_canonical_signal_history(base)["signal"]
    prices = load_subsector_prices(start="2016-09-01").sort_index()
    subsector_frame = build_subsector_frame(prices)

    prior_dates = independent(
        [d for d in episode_starts(signals) if d in subsector_frame.index and d < as_of],
        prices.index,
    )
    live_dates = [*prior_dates, as_of]
    current_i = len(live_dates) - 1

    results = []
    for candidate in published:
        sym = candidate["symbol"]
        engine_prediction = predict_for_symbol(prices, subsector_frame, live_dates, current_i, sym)
        if engine_prediction is None:
            raise RuntimeError(f"Frozen engine returned no prediction for {sym}")
        detail = reconstruct(prices, subsector_frame, prior_dates, as_of, sym)
        published_score = float(candidate["predicted_median_excess_vs_spy"])
        published_rate = float(candidate["neighbor_positive_excess_rate"])
        score_diff = abs(detail["reconstructed_score"] - published_score)
        rate_diff = abs(detail["reconstructed_positive_rate"] - published_rate)
        engine_diff = abs(float(engine_prediction["score"]) - published_score)
        passed = score_diff <= TOLERANCE and rate_diff <= TOLERANCE and engine_diff <= TOLERANCE
        results.append({
            "symbol": sym,
            "published_score": published_score,
            "engine_score": float(engine_prediction["score"]),
            "reconstructed_score": detail["reconstructed_score"],
            "published_positive_rate": published_rate,
            "reconstructed_positive_rate": detail["reconstructed_positive_rate"],
            "neighbors": detail["neighbors"],
            "pass": passed,
        })
        if not passed:
            raise AssertionError(f"Opportunity reproducibility failed for {sym}: {results[-1]}")

    output = {
        "status": "PASS",
        "as_of": str(as_of.date()),
        "target_definition": "For each prior neighbor, average 10D and 30D forward excess return vs SPY; candidate score is the median of those averages across the 15 nearest prior RE-ENTRY states.",
        "results": results,
    }
    out = Path("artifacts/reentry_opportunity_repro_audit")
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
