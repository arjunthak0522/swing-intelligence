from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from internal_correction_full_v2 import build_full_v2_state
from internal_correction_v2 import build_cross_section, load_prices, v1_weakness
from reentry_confidence import feature_frame

ENGINE_VERSION = "reentry_v2.0-research"


def classify_setup(row: pd.Series) -> tuple[str, str]:
    """Return one canonical setup type and one operational decision.

    The old broad-market weakness rule remains only as an internal component.
    V2 is the engine and all sector/factor state is evaluated before deciding.
    """
    broad_component = bool(row["broad_market_weakness"])
    developing = bool(row["v2_developing"])
    meaningful = bool(row["v2_meaningful"])
    broad_reset = bool(row["v2_broad"])
    stabilizing = bool(row["v2_stabilizing"])

    if meaningful and stabilizing:
        if broad_component:
            return "BROAD_CORRECTION", "RE-ENTER"
        return "ROLLING_INTERNAL_CORRECTION", "RE-ENTER"

    if broad_component and not stabilizing:
        return "BROAD_CORRECTION", "WAIT"

    if developing:
        return "DEVELOPING_INTERNAL_RESET", "WAIT"

    return "NO_MEANINGFUL_SETUP", "NO RE-ENTRY SETUP"


def factor_state(row: pd.Series) -> str:
    labels: list[str] = []
    if bool(row["v2_momentum_reset"]):
        labels.append("MOMENTUM RESET")
    if bool(row["v2_growth_reset"]):
        labels.append("GROWTH RESET")
    if bool(row["v2_quality_over_momentum"]):
        labels.append("QUALITY LEADERSHIP")
    if bool(row["v2_small_vs_large_reset"]):
        labels.append("SMALL VS LARGE RESET")
    return " / ".join(labels) if labels else "NO MATERIAL FACTOR RESET"


def build_engine_frame() -> pd.DataFrame:
    base = feature_frame(require_same_day=False)
    prices = load_prices()
    xs = build_cross_section(prices)
    df = base.join(xs, how="inner").dropna(subset=["spy_dd20", "sector_dispersion_pct"]).copy()

    # Legacy V1 naming is intentionally removed from the canonical engine surface.
    # This is the validated broad-market component carried forward into V2.
    df["broad_market_weakness"] = v1_weakness(df)
    df = build_full_v2_state(df)

    classified = df.apply(classify_setup, axis=1)
    df["setup_type"] = [x[0] for x in classified]
    df["decision"] = [x[1] for x in classified]
    df["factor_state"] = df.apply(factor_state, axis=1)
    return df


def latest_payload(df: pd.DataFrame) -> dict:
    row = df.iloc[-1]
    if bool(row["v2_broad"]):
        internal_reset = "BROAD"
    elif bool(row["v2_meaningful"]):
        internal_reset = "MEANINGFUL"
    elif bool(row["v2_developing"]):
        internal_reset = "DEVELOPING"
    else:
        internal_reset = "NONE"

    selling_pressure = "STABILIZING" if bool(row["v2_stabilizing"]) else "WORSENING"

    return {
        "engine": "RE-ENTRY",
        "engine_version": ENGINE_VERSION,
        "date": str(df.index[-1].date()),
        "setup_type": row["setup_type"],
        "decision": row["decision"],
        "market_damage_component_active": bool(row["broad_market_weakness"]),
        "internal_reset": internal_reset,
        "selling_pressure": selling_pressure,
        "factor_state": row["factor_state"],
        "hidden_reset": bool(row["v2_hidden_reset"]),
        "sector_damage_share_2": float(row["v2_sector_damage_share_2"]),
        "factor_damage_share_2": float(row["v2_factor_damage_share_2"]),
        "damage_bucket_count": int(row["v2_damage_bucket_count"]),
        "rotation_count": int(row["v2_rotation_count"]),
        "research_only": True,
        "proxy_caveat": "Sector and factor histories use liquid ETF proxies and are not proprietary point-in-time factor-index constituent histories.",
    }


def main() -> None:
    df = build_engine_frame()
    payload = latest_payload(df)
    out = Path("artifacts/internal_correction_v2")
    out.mkdir(parents=True, exist_ok=True)
    (out / "reentry_v2_latest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
