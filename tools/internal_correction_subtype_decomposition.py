from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from internal_correction_v2 import (
    FACTORS,
    HORIZONS,
    SECTORS,
    build_cross_section,
    cooldown_dates,
    forward_stats,
    load_prices,
    v1_weakness,
)
from reentry_confidence import feature_frame

ROUND_TRIP_COST = 0.001
RNG = np.random.default_rng(20260904)
MATCH_FEATURES = ["spy_dd20", "B50", "B200", "b50_change3", "vix_change5", "curve_ratio"]
ERAS = {
    "2016_2020": (pd.Timestamp("2016-01-01"), pd.Timestamp("2020-12-31")),
    "2021_present": (pd.Timestamp("2021-01-01"), pd.Timestamp.max),
    "covid_2020": (pd.Timestamp("2020-02-01"), pd.Timestamp("2020-12-31")),
    "bear_2022": (pd.Timestamp("2022-01-01"), pd.Timestamp("2022-12-31")),
    "2023_present": (pd.Timestamp("2023-01-01"), pd.Timestamp.max),
}


def load_qqq_proxies(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Free ETF proxies for Nasdaq leadership research only."""
    import yfinance as yf

    symbols = ["SMH", "RSP", "RSPT"]
    raw = yf.download(
        symbols,
        start="2016-09-01",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw.empty or not isinstance(raw.columns, pd.MultiIndex):
        return pd.DataFrame(index=index)
    closes = raw["Close"].copy()
    closes.index = pd.to_datetime(closes.index).tz_localize(None).normalize()
    closes = closes.sort_index().apply(pd.to_numeric, errors="coerce")
    return closes.reindex(index)


def add_extra_features(df: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    spy = prices["SPY"]
    qqq = prices["QQQ"]

    # Cross-sectional aggregates useful for subtype attribution.
    sector_dd = pd.DataFrame({s: out[f"{s}_dd20"] for s in SECTORS})
    factor_dd = pd.DataFrame({s: out[f"{s}_dd20"] for s in FACTORS})
    sector_rs = pd.DataFrame({s: out[f"{s}_rs20"] for s in SECTORS})
    factor_rs = pd.DataFrame({s: out[f"{s}_rs20"] for s in FACTORS})

    out["sector_damage_4"] = (sector_dd <= -0.04).sum(axis=1)
    out["factor_damage_4"] = (factor_dd <= -0.04).sum(axis=1)
    out["sector_negative_rs"] = (sector_rs < -0.02).sum(axis=1)
    out["factor_negative_rs"] = (factor_rs < -0.02).sum(axis=1)
    out["sector_rs_dispersion20"] = sector_rs.std(axis=1)
    out["factor_rs_dispersion20"] = factor_rs.std(axis=1)

    # Leadership and concentration proxies already available in the frozen ETF set.
    out["tech_dd20"] = out["XLK_dd20"]
    out["momentum_dd20"] = out["MTUM_dd20"]
    out["growth_dd20"] = out["IWF_dd20"]
    out["quality_dd20"] = out["QUAL_dd20"]
    out["small_vs_spy_20"] = prices["IWM"].pct_change(20) - spy.pct_change(20)
    out["qqq_vs_spy_20"] = qqq.pct_change(20) - spy.pct_change(20)

    # Optional QQQ-specific free proxies. RSPT has a shorter history, so any subtype
    # requiring it naturally has fewer events and must be treated accordingly.
    qprox = load_qqq_proxies(out.index)
    if "SMH" in qprox:
        out["smh_dd20"] = qprox["SMH"] / qprox["SMH"].rolling(20).max() - 1.0
        out["smh_ret5"] = qprox["SMH"].pct_change(5)
        out["smh_vs_qqq_20"] = qprox["SMH"].pct_change(20) - qqq.pct_change(20)
    else:
        out["smh_dd20"] = np.nan
        out["smh_ret5"] = np.nan
        out["smh_vs_qqq_20"] = np.nan

    if "RSP" in qprox:
        out["rsp_vs_spy_20"] = qprox["RSP"].pct_change(20) - spy.pct_change(20)
        out["rsp_ret5"] = qprox["RSP"].pct_change(5)
    else:
        out["rsp_vs_spy_20"] = np.nan
        out["rsp_ret5"] = np.nan

    if "RSPT" in qprox:
        out["rspt_vs_xlk_20"] = qprox["RSPT"].pct_change(20) - prices["XLK"].pct_change(20)
    else:
        out["rspt_vs_xlk_20"] = np.nan

    return out


def stabilizing(df: pd.DataFrame) -> pd.Series:
    return (
        (df["sector_repair"] >= 2)
        | (df["factor_repair"] >= 2)
        | ((df["sector_median_ret1"] > 0) & (df["factor_median_ret1"] > 0))
    )


def subtype_masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    shallow = df["spy_dd20"] > -0.03
    stab = stabilizing(df)
    high_disp = df["sector_dispersion_pct"] >= 0.80

    sector = shallow & (df["sector_damage_3"] >= 4) & stab
    factor = shallow & (df["factor_damage_3"] >= 3) & stab
    sector_factor = sector & factor
    dispersion = shallow & high_disp & (df["sector_damage_2"] >= 3) & stab

    momentum_unwind = (
        shallow
        & ((df["momentum_dd20"] <= -0.03) | (df["momentum_relative_20"] <= -0.03))
        & ((df["factor_repair"] >= 1) | (df["quality_minus_momentum_20"] > 0))
    )
    growth_value = (
        shallow
        & ((df["growth_dd20"] <= -0.03) | (df["growth_minus_value_20"] <= -0.02))
        & ((df["factor_repair"] >= 1) | (df["factor_median_ret1"] > 0))
    )
    momentum_quality = (
        shallow
        & ((df["momentum_dd20"] <= -0.03) | (df["momentum_relative_20"] <= -0.03))
        & (df["quality_minus_momentum_20"] >= 0.02)
    )
    leadership_reset = (
        shallow
        & ((df["XLK_dd20"] <= -0.03) | (df["MTUM_dd20"] <= -0.03) | (df["IWF_dd20"] <= -0.03))
        & (df["sector_repair"] >= 2)
        & (df["sector_median_ret1"] > 0)
    )
    concentration = (
        shallow
        & ((df["qqq_vs_spy_20"] <= -0.02) | (df["XLK_dd20"] <= -0.03))
        & ((df["rsp_vs_spy_20"] > 0) | (df["small_vs_spy_20"] > 0))
        & ((df["sector_repair"] >= 2) | (df["sector_median_ret1"] > 0))
    )
    qqq_specific = (
        (df["QQQ_dd20_proxy"] > -0.04)
        & (
            (df["XLK_dd20"] <= -0.03)
            | (df["smh_dd20"] <= -0.04)
            | (df["MTUM_dd20"] <= -0.03)
            | (df["IWF_dd20"] <= -0.03)
        )
        & (
            (df["sector_repair"] >= 2)
            | (df["factor_repair"] >= 2)
            | (df["smh_ret5"] > 0)
        )
    )

    return {
        "sector_correction_only": sector & ~factor,
        "factor_correction_only": factor & ~sector,
        "sector_and_factor": sector_factor,
        "high_dispersion_rotation": dispersion & ~sector_factor,
        "momentum_unwind": momentum_unwind,
        "growth_vs_value_rotation": growth_value,
        "momentum_vs_quality_rotation": momentum_quality,
        "leadership_reset": leadership_reset,
        "concentration_correction": concentration,
        "qqq_specific_internal_correction": qqq_specific,
    }


def raw_outcome(prices: pd.DataFrame, date: pd.Timestamp, symbol: str, horizon: int) -> tuple[float, float] | None:
    s = prices[symbol].dropna()
    if date not in s.index:
        return None
    pos = s.index.get_loc(date)
    if not isinstance(pos, (int, np.integer)) or pos + 1 + horizon >= len(s):
        return None
    entry = float(s.iloc[pos + 1])
    path = s.iloc[pos + 1:pos + 1 + horizon + 1].astype(float)
    ret = float(path.iloc[-1] / entry - 1.0 - ROUND_TRIP_COST)
    mae = float((path / entry - 1.0).min())
    return ret, mae


def nearest_control(df: pd.DataFrame, date: pd.Timestamp, signal: pd.Series, *, same_v1: bool = True) -> pd.Timestamp | None:
    loc = df.index.get_loc(date)
    if not isinstance(loc, (int, np.integer)) or loc < 252:
        return None
    # Prior-only matching avoids using future market states as controls.
    hist = df.iloc[: max(0, loc - 20)].copy()
    sig = signal.reindex(hist.index).fillna(False)
    hist = hist[(hist["spy_dd20"] > -0.03) & (~sig)]
    if same_v1:
        hist = hist[hist["v1_weakness"] == bool(df.loc[date, "v1_weakness"])]
    if hist.empty:
        return None

    x = hist[MATCH_FEATURES].replace([np.inf, -np.inf], np.nan).dropna()
    if x.empty:
        return None
    target = df.loc[date, MATCH_FEATURES].astype(float)
    mu = x.mean()
    sd = x.std().replace(0, np.nan)
    z = (x - mu) / sd
    zt = (target - mu) / sd
    dist = ((z - zt) ** 2).mean(axis=1) ** 0.5

    # Gentle era penalty. It does not force same-year matching but prevents a
    # structurally distant era from winning on a tiny feature-distance difference.
    year_gap = pd.Series(np.abs(x.index.year - date.year), index=x.index, dtype=float)
    dist = dist + 0.05 * year_gap
    dist = dist.replace([np.inf, -np.inf], np.nan).dropna()
    return None if dist.empty else pd.Timestamp(dist.idxmin())


def bootstrap_median(values: np.ndarray, reps: int = 3000) -> list[float | None]:
    if len(values) < 5:
        return [None, None]
    idx = RNG.integers(0, len(values), size=(reps, len(values)))
    meds = np.median(values[idx], axis=1)
    return [float(np.quantile(meds, 0.025)), float(np.quantile(meds, 0.975))]


def matched_control_stats(df: pd.DataFrame, prices: pd.DataFrame, dates: list[pd.Timestamp], signal: pd.Series) -> dict:
    pairs = []
    for dt in dates:
        ctrl = nearest_control(df, dt, signal, same_v1=True)
        if ctrl is not None:
            pairs.append((dt, ctrl))

    result = {"pair_count": len(pairs), "SPY": {}, "QQQ": {}}
    for symbol in ["SPY", "QQQ"]:
        for h in HORIZONS:
            diffs, mae_diffs = [], []
            for sig, ctrl in pairs:
                a = raw_outcome(prices, sig, symbol, h)
                b = raw_outcome(prices, ctrl, symbol, h)
                if a is None or b is None:
                    continue
                diffs.append(a[0] - b[0])
                mae_diffs.append(a[1] - b[1])
            arr = np.asarray(diffs, dtype=float)
            arr_mae = np.asarray(mae_diffs, dtype=float)
            result[symbol][str(h)] = {
                "n": int(len(arr)),
                "median_return_advantage": float(np.median(arr)) if len(arr) else None,
                "return_advantage_ci95": bootstrap_median(arr),
                "fraction_signal_better": float((arr > 0).mean()) if len(arr) else None,
                "median_mae_advantage": float(np.median(arr_mae)) if len(arr_mae) else None,
                "mae_advantage_ci95": bootstrap_median(arr_mae),
            }
    return result


def era_dates(dates: list[pd.Timestamp]) -> dict[str, list[pd.Timestamp]]:
    out = {}
    for name, (start, end) in ERAS.items():
        out[name] = [d for d in dates if start <= d <= end]
    return out


def subtype_summary(df: pd.DataFrame, prices: pd.DataFrame, name: str, mask: pd.Series, cooldown: int = 10) -> dict:
    dates = cooldown_dates(mask.fillna(False), cooldown)
    missed = cooldown_dates((mask & ~df["v1_weakness"]).fillna(False), cooldown)
    eras = era_dates(dates)
    return {
        "event_count": len(dates),
        "v1_missed_count": len(missed),
        "outcomes": {s: {str(h): forward_stats(prices, dates, s, h) for h in HORIZONS} for s in ["SPY", "QQQ"]},
        "v1_missed_outcomes": {s: {str(h): forward_stats(prices, missed, s, h) for h in HORIZONS} for s in ["SPY", "QQQ"]},
        "era_event_counts": {k: len(v) for k, v in eras.items()},
        "era_outcomes": {
            era: {s: {str(h): forward_stats(prices, ds, s, h) for h in HORIZONS} for s in ["SPY", "QQQ"]}
            for era, ds in eras.items()
        },
        "matched_controls": matched_control_stats(df, prices, dates, mask),
    }


def robustness_for_family(df: pd.DataFrame, prices: pd.DataFrame) -> list[dict]:
    """Predeclared nearby thresholds. No optimization or winner selection."""
    rows = []
    shallow = df["spy_dd20"] > -0.03
    stab = stabilizing(df)
    for sector_n in [3, 4, 5]:
        for factor_n in [2, 3, 4]:
            for dd in [0.02, 0.03, 0.04]:
                sector_damage = sum((df[f"{s}_dd20"] <= -dd).astype(int) for s in SECTORS)
                factor_damage = sum((df[f"{s}_dd20"] <= -dd).astype(int) for s in FACTORS)
                mask = shallow & ((sector_damage >= sector_n) | (factor_damage >= factor_n)) & stab
                for cooldown in [5, 10, 15]:
                    dates = cooldown_dates(mask.fillna(False), cooldown)
                    spy30 = forward_stats(prices, dates, "SPY", 30)
                    qqq30 = forward_stats(prices, dates, "QQQ", 30)
                    rows.append({
                        "sector_count": sector_n,
                        "factor_count": factor_n,
                        "drawdown_threshold": dd,
                        "cooldown": cooldown,
                        "events": len(dates),
                        "SPY_30D_median": spy30.get("median_return"),
                        "SPY_30D_positive_rate": spy30.get("positive_rate"),
                        "QQQ_30D_median": qqq30.get("median_return"),
                        "QQQ_30D_positive_rate": qqq30.get("positive_rate"),
                    })
    return rows


def evidence_classification(summary: dict) -> dict:
    """Mechanical research triage, not a production decision rule."""
    out = {}
    for name, r in summary.items():
        n = r["event_count"]
        spy30 = r["outcomes"]["SPY"]["30"]
        qqq30 = r["outcomes"]["QQQ"]["30"]
        mspy = r["matched_controls"]["SPY"]["30"]
        mqqq = r["matched_controls"]["QQQ"]["30"]
        era_counts = r["era_event_counts"]
        both_eras = era_counts["2016_2020"] >= 8 and era_counts["2021_present"] >= 8
        raw_ok = (
            spy30.get("median_return") is not None and spy30.get("median_return", -1) > 0
            and qqq30.get("median_return") is not None and qqq30.get("median_return", -1) > 0
        )
        matched_ok = (
            mspy.get("median_return_advantage") is not None and mspy["median_return_advantage"] > 0
            and mqqq.get("median_return_advantage") is not None and mqqq["median_return_advantage"] > 0
        )
        if n >= 30 and both_eras and raw_ok and matched_ok:
            cls = "SUPPORTING_CANDIDATE"
        elif n >= 15 and raw_ok:
            cls = "EXPERIMENTAL_PROMISING"
        else:
            cls = "EXPERIMENTAL"
        out[name] = {
            "classification": cls,
            "reason": {
                "events": n,
                "both_eras_minimum_met": both_eras,
                "positive_30D_raw_both_assets": raw_ok,
                "positive_30D_matched_advantage_both_assets": matched_ok,
            },
        }
    return out


def main() -> None:
    base = feature_frame(require_same_day=False)
    prices = load_prices()
    xs = build_cross_section(prices)
    df = base.join(xs, how="inner").dropna(subset=["spy_dd20", "sector_dispersion_pct"]).copy()
    df["v1_weakness"] = v1_weakness(df)
    df["QQQ_dd20_proxy"] = prices["QQQ"] / prices["QQQ"].rolling(20).max() - 1.0
    df = add_extra_features(df, prices)

    masks = subtype_masks(df)
    summaries = {name: subtype_summary(df, prices, name, mask) for name, mask in masks.items()}
    classifications = evidence_classification(summaries)

    result = {
        "status": "RESEARCH_ONLY_DO_NOT_PROMOTE_OR_DEPLOY",
        "sample_start": str(df.index.min().date()),
        "sample_end": str(df.index.max().date()),
        "methodology": {
            "entry": "next session close after signal date",
            "round_trip_cost": ROUND_TRIP_COST,
            "horizons": HORIZONS,
            "primary_cooldown": 10,
            "matched_controls": "prior-only nearest shallow-SPY control matched on V1 state, SPY drawdown, breadth, volatility, and curve ratio, with a gentle era-distance penalty",
            "classification_note": "Mechanical triage is intentionally conservative and is not a production rule.",
        },
        "subtypes": summaries,
        "mechanical_research_classification": classifications,
        "family_threshold_robustness": robustness_for_family(df, prices),
        "proxy_caveat": "Sector and factor histories use liquid ETF proxies and are not proprietary point-in-time factor-index constituent histories.",
        "qqq_proxy_caveat": "QQQ-specific research uses free ETF proxies including XLK, SMH, MTUM, IWF, RSP, and RSPT where history is available. RSPT has shorter history and should not be over-interpreted.",
    }

    out = Path("artifacts/internal_correction_v2")
    out.mkdir(parents=True, exist_ok=True)
    (out / "subtype_decomposition.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
