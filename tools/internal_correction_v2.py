from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_confidence import feature_frame

SECTORS = ["XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLB", "XLRE", "XLK", "XLU"]
FACTORS = ["MTUM", "QUAL", "VLUE", "IWF", "IWD", "USMV", "SPYD", "IWM"]
SYMBOLS = ["SPY", "QQQ", *SECTORS, *FACTORS]
HORIZONS = [5, 7, 10, 15, 30, 60]
ROUND_TRIP_COST = 0.001
START = "2016-09-01"
PRIMARY_COOLDOWN = 10


def load_prices() -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(
        SYMBOLS,
        start=START,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw.empty or not isinstance(raw.columns, pd.MultiIndex):
        raise RuntimeError("Yahoo cross-sectional price download failed")
    closes = raw["Close"].copy()
    closes.index = pd.to_datetime(closes.index).tz_localize(None).normalize()
    closes = closes.sort_index().apply(pd.to_numeric, errors="coerce")
    required = ["SPY", "QQQ"]
    if any(s not in closes.columns for s in required):
        raise RuntimeError("SPY/QQQ missing from cross-sectional dataset")
    return closes


def dd_from_high(s: pd.Series, window: int) -> pd.Series:
    return s / s.rolling(window).max() - 1.0


def percentile_rank_trailing(s: pd.Series, window: int = 252) -> pd.Series:
    def rank_last(x: pd.Series) -> float:
        a = np.asarray(x, dtype=float)
        if np.isnan(a[-1]):
            return np.nan
        valid = a[np.isfinite(a)]
        if len(valid) < max(60, window // 4):
            return np.nan
        return float((valid <= a[-1]).mean())
    return s.rolling(window, min_periods=max(60, window // 4)).apply(rank_last, raw=False)


def build_cross_section(prices: pd.DataFrame) -> pd.DataFrame:
    spy = prices["SPY"]
    out = pd.DataFrame(index=prices.index)
    out["spy_dd20_xs"] = dd_from_high(spy, 20)

    sector_ret1 = prices[SECTORS].pct_change(1)
    sector_ret5 = prices[SECTORS].pct_change(5)
    sector_ret20 = prices[SECTORS].pct_change(20)
    sector_dd20 = prices[SECTORS] / prices[SECTORS].rolling(20).max() - 1.0
    sector_dd60 = prices[SECTORS] / prices[SECTORS].rolling(60).max() - 1.0

    factor_ret1 = prices[FACTORS].pct_change(1)
    factor_ret5 = prices[FACTORS].pct_change(5)
    factor_ret20 = prices[FACTORS].pct_change(20)
    factor_dd20 = prices[FACTORS] / prices[FACTORS].rolling(20).max() - 1.0
    factor_dd60 = prices[FACTORS] / prices[FACTORS].rolling(60).max() - 1.0

    out["sector_damage_3"] = (sector_dd20 <= -0.03).sum(axis=1)
    out["sector_damage_5"] = (sector_dd20 <= -0.05).sum(axis=1)
    out["sector_damage_2"] = (sector_dd20 <= -0.02).sum(axis=1)
    out["sector_repair"] = ((sector_dd20 <= -0.03) & (sector_ret5 > 0)).sum(axis=1)
    out["sector_dispersion20"] = sector_ret20.std(axis=1)
    out["sector_dispersion_pct"] = percentile_rank_trailing(out["sector_dispersion20"])
    out["sector_median_ret1"] = sector_ret1.median(axis=1)
    out["sector_median_dd20"] = sector_dd20.median(axis=1)
    out["sector_median_dd60"] = sector_dd60.median(axis=1)

    out["factor_damage_3"] = (factor_dd20 <= -0.03).sum(axis=1)
    out["factor_damage_2"] = (factor_dd20 <= -0.02).sum(axis=1)
    out["factor_repair"] = ((factor_dd20 <= -0.03) & (factor_ret5 > 0)).sum(axis=1)
    out["factor_dispersion20"] = factor_ret20.std(axis=1)
    out["factor_median_ret1"] = factor_ret1.median(axis=1)
    out["factor_median_dd20"] = factor_dd20.median(axis=1)
    out["factor_median_dd60"] = factor_dd60.median(axis=1)

    spy_ret20 = spy.pct_change(20)
    spy_ret60 = spy.pct_change(60)
    for symbol in SECTORS + FACTORS:
        out[f"{symbol}_dd20"] = dd_from_high(prices[symbol], 20)
        out[f"{symbol}_dd60"] = dd_from_high(prices[symbol], 60)
        out[f"{symbol}_rs20"] = prices[symbol].pct_change(20) - spy_ret20
        out[f"{symbol}_rs60"] = prices[symbol].pct_change(60) - spy_ret60

    out["growth_minus_value_20"] = factor_ret20["IWF"] - factor_ret20["IWD"]
    out["quality_minus_momentum_20"] = factor_ret20["QUAL"] - factor_ret20["MTUM"]
    out["momentum_relative_20"] = factor_ret20["MTUM"] - spy_ret20
    return out


def v1_weakness(frame: pd.DataFrame) -> pd.Series:
    return (
        (frame["spy_dd20"] <= -0.01)
        | (frame["B50"] <= 0.50)
        | (frame["vix_change5"] >= 0.10)
        | (frame["curve_ratio"] >= 1.0)
    )


def primary_internal_signal(df: pd.DataFrame) -> pd.Series:
    shallow = df["spy_dd20"] > -0.03
    damage = (
        (df["sector_damage_3"] >= 4)
        | (df["factor_damage_3"] >= 3)
        | ((df["sector_dispersion_pct"] >= 0.80) & (df["sector_damage_2"] >= 3))
    )
    stabilizing = (
        (df["sector_repair"] >= 2)
        | (df["factor_repair"] >= 2)
        | ((df["sector_median_ret1"] > 0) & (df["factor_median_ret1"] > 0))
    )
    return shallow & damage & stabilizing


def cooldown_dates(mask: pd.Series, cooldown: int) -> list[pd.Timestamp]:
    dates: list[pd.Timestamp] = []
    last_pos = -10_000
    idx = list(mask.index)
    for pos, dt in enumerate(idx):
        if bool(mask.iloc[pos]) and pos - last_pos > cooldown:
            dates.append(pd.Timestamp(dt))
            last_pos = pos
    return dates


def forward_stats(prices: pd.DataFrame, dates: list[pd.Timestamp], symbol: str, horizon: int) -> dict:
    s = prices[symbol].dropna()
    rows = []
    for dt in dates:
        if dt not in s.index:
            continue
        pos = s.index.get_loc(dt)
        if not isinstance(pos, (int, np.integer)) or pos + 1 + horizon >= len(s):
            continue
        entry = float(s.iloc[pos + 1])
        path = s.iloc[pos + 1: pos + 1 + horizon + 1].astype(float)
        final = float(path.iloc[-1] / entry - 1.0 - ROUND_TRIP_COST)
        path_ret = path / entry - 1.0
        rows.append({"ret": final, "mae": float(path_ret.min()), "mfe": float(path_ret.max())})
    if not rows:
        return {"n": 0}
    d = pd.DataFrame(rows)
    return {
        "n": int(len(d)),
        "median_return": float(d.ret.median()),
        "mean_return": float(d.ret.mean()),
        "positive_rate": float((d.ret > 0).mean()),
        "p25_return": float(d.ret.quantile(0.25)),
        "p10_return": float(d.ret.quantile(0.10)),
        "median_mae": float(d.mae.median()),
        "p10_mae": float(d.mae.quantile(0.10)),
        "worst_mae": float(d.mae.min()),
        "median_mfe": float(d.mfe.median()),
    }


def summarize_group(prices: pd.DataFrame, dates: list[pd.Timestamp]) -> dict:
    return {
        symbol: {str(h): forward_stats(prices, dates, symbol, h) for h in HORIZONS}
        for symbol in ["SPY", "QQQ"]
    }


def threshold_robustness(df: pd.DataFrame, prices: pd.DataFrame) -> list[dict]:
    rows = []
    for sector_n in [3, 4, 5]:
        for factor_n in [2, 3, 4]:
            for dd in [0.02, 0.03, 0.04]:
                sector_damage = sum((df[f"{s}_dd20"] <= -dd).astype(int) for s in SECTORS)
                factor_damage = sum((df[f"{s}_dd20"] <= -dd).astype(int) for s in FACTORS)
                mask = (
                    (df["spy_dd20"] > -0.03)
                    & ((sector_damage >= sector_n) | (factor_damage >= factor_n))
                    & ((df["sector_repair"] >= 2) | (df["factor_repair"] >= 2) | ((df["sector_median_ret1"] > 0) & (df["factor_median_ret1"] > 0)))
                )
                dates = cooldown_dates(mask.fillna(False), PRIMARY_COOLDOWN)
                stat = forward_stats(prices, dates, "SPY", 10)
                rows.append({
                    "sector_n": sector_n,
                    "factor_n": factor_n,
                    "drawdown": dd,
                    "events": len(dates),
                    "spy10_median": stat.get("median_return"),
                    "spy10_positive": stat.get("positive_rate"),
                })
    return rows


def main() -> None:
    base = feature_frame(require_same_day=False)
    prices = load_prices()
    xs = build_cross_section(prices)
    df = base.join(xs, how="inner").dropna(subset=["spy_dd20", "sector_dispersion_pct"])
    df["v1_weakness"] = v1_weakness(df)
    df["internal_primary"] = primary_internal_signal(df)

    primary_dates = cooldown_dates(df["internal_primary"].fillna(False), PRIMARY_COOLDOWN)
    missed_dates = cooldown_dates((df["internal_primary"] & ~df["v1_weakness"]).fillna(False), PRIMARY_COOLDOWN)
    v1_plus_internal_dates = cooldown_dates((df["internal_primary"] & df["v1_weakness"]).fillna(False), PRIMARY_COOLDOWN)

    era1 = [d for d in primary_dates if d < pd.Timestamp("2021-01-01")]
    era2 = [d for d in primary_dates if d >= pd.Timestamp("2021-01-01")]

    latest = df.iloc[-1]
    result = {
        "research_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
        "sample_start": str(df.index.min().date()),
        "sample_end": str(df.index.max().date()),
        "primary_event_count": len(primary_dates),
        "v1_missed_internal_event_count": len(missed_dates),
        "v1_overlap_event_count": len(v1_plus_internal_dates),
        "era_event_counts": {"2016_2020": len(era1), "2021_present": len(era2)},
        "primary": summarize_group(prices, primary_dates),
        "v1_missed": summarize_group(prices, missed_dates),
        "era_2016_2020": summarize_group(prices, era1),
        "era_2021_present": summarize_group(prices, era2),
        "threshold_robustness": threshold_robustness(df, prices),
        "latest_internal_state": {
            "date": str(df.index[-1].date()),
            "spy_dd20": float(latest["spy_dd20"]),
            "v1_weakness": bool(latest["v1_weakness"]),
            "internal_primary": bool(latest["internal_primary"]),
            "sector_damage_3": int(latest["sector_damage_3"]),
            "sector_damage_5": int(latest["sector_damage_5"]),
            "sector_repair": int(latest["sector_repair"]),
            "factor_damage_3": int(latest["factor_damage_3"]),
            "factor_repair": int(latest["factor_repair"]),
            "sector_dispersion_pct": float(latest["sector_dispersion_pct"]),
            "growth_minus_value_20": float(latest["growth_minus_value_20"]),
            "quality_minus_momentum_20": float(latest["quality_minus_momentum_20"]),
            "momentum_relative_20": float(latest["momentum_relative_20"]),
        },
        "proxy_caveat": "Sector and factor histories use liquid ETF proxies and are not proprietary point-in-time factor-index constituent histories.",
    }

    out = Path("artifacts/internal_correction_v2")
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
