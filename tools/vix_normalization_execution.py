from __future__ import annotations

from io import StringIO
import json
import math
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd

SEED = 20260903
BOOTSTRAPS = 10000
ROUNDTRIP_COST_BPS = 10.0  # 5 bps entry + 5 bps exit
COOLDOWN_DAYS = 10


def fetch_fred(series_id: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    with urlopen(url, timeout=30) as resp:  # nosec - fixed HTTPS FRED endpoint
        text = resp.read().decode("utf-8")
    df = pd.read_csv(StringIO(text))
    df.columns = ["date", series_id]
    df["date"] = pd.to_datetime(df["date"])
    df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
    return df.dropna().set_index("date")[series_id].sort_index()


def fetch_twelve_close(symbol: str, start: str = "2007-12-01") -> pd.Series:
    key = os.environ["TWELVE_DATA_API_KEY"]
    params = {
        "symbol": symbol,
        "interval": "1day",
        "start_date": start,
        "outputsize": 5000,
        "apikey": key,
        "format": "JSON",
        "order": "ASC",
    }
    url = "https://api.twelvedata.com/time_series?" + urlencode(params)
    with urlopen(url, timeout=60) as resp:  # nosec - fixed HTTPS Twelve Data endpoint
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("status") == "error" or "values" not in payload:
        raise RuntimeError(payload.get("message", f"No data for {symbol}"))
    df = pd.DataFrame(payload["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna(subset=["close"]).set_index("datetime")["close"].sort_index().rename(symbol)


def normalization_signal(vix: pd.Series, vix3m: pd.Series) -> pd.Series:
    curve = pd.concat([vix.rename("VIX"), vix3m.rename("VIX3M")], axis=1).dropna()
    ratio = curve["VIX"] / curve["VIX3M"]
    return ((ratio.shift(1) > 1.0) & (ratio <= 1.0)).rename("signal")


def candidate_signal_dates(signal: pd.Series, trading_index: pd.DatetimeIndex, cooldown: int = COOLDOWN_DAYS) -> list[pd.Timestamp]:
    aligned = signal.reindex(trading_index).fillna(False).astype(bool)
    dates: list[pd.Timestamp] = []
    last_pos = -10_000
    for pos, (d, flag) in enumerate(aligned.items()):
        if bool(flag) and pos - last_pos > cooldown:
            dates.append(d)
            last_pos = pos
    return dates


def simulate_trades(
    price: pd.Series,
    signals: list[pd.Timestamp],
    hold_days: int,
    roundtrip_cost_bps: float = ROUNDTRIP_COST_BPS,
    stop_pct: float | None = None,
) -> pd.DataFrame:
    idx = price.index
    rows = []
    unavailable_until = -1
    cost = roundtrip_cost_bps / 10000.0
    for signal_date in signals:
        if signal_date not in idx:
            continue
        signal_pos = idx.get_loc(signal_date)
        if not isinstance(signal_pos, (int, np.integer)):
            continue
        entry_pos = int(signal_pos) + 1  # signal known at t close, enter at t+1 close
        if entry_pos <= unavailable_until or entry_pos >= len(idx):
            continue
        planned_exit = entry_pos + hold_days
        if planned_exit >= len(idx):
            continue
        entry_px = float(price.iloc[entry_pos])
        exit_pos = planned_exit
        stop_hit = False
        if stop_pct is not None:
            for p in range(entry_pos + 1, planned_exit + 1):
                if float(price.iloc[p]) / entry_px - 1.0 <= -stop_pct:
                    exit_pos = p
                    stop_hit = True
                    break
        path = price.iloc[entry_pos : exit_pos + 1].astype(float) / entry_px - 1.0
        gross = float(price.iloc[exit_pos]) / entry_px - 1.0
        net = (1.0 + gross) * (1.0 - cost) - 1.0
        rows.append({
            "signal_date": signal_date,
            "entry_date": idx[entry_pos],
            "exit_date": idx[exit_pos],
            "gross_return": gross,
            "net_return": net,
            "mae": float(path.min()),
            "mfe": float(path.max()),
            "stop_hit": stop_hit,
            "days_held": int(exit_pos - entry_pos),
        })
        unavailable_until = exit_pos
    if not rows:
        return pd.DataFrame(columns=["net_return", "gross_return", "mae", "mfe"])
    return pd.DataFrame(rows).set_index("signal_date")


def profit_factor(returns: pd.Series) -> float | None:
    wins = float(returns[returns > 0].sum())
    losses = float(-returns[returns < 0].sum())
    if losses == 0:
        return None
    return wins / losses


def max_drawdown_from_trades(returns: pd.Series) -> float | None:
    if returns.empty:
        return None
    equity = (1.0 + returns).cumprod()
    dd = equity / equity.cummax() - 1.0
    return float(dd.min())


def baseline_next_close(price: pd.Series, hold_days: int, cost_bps: float) -> pd.Series:
    # Entry at next close and exit hold_days after entry, matching executable timing.
    gross = price.shift(-(hold_days + 1)) / price.shift(-1) - 1.0
    return ((1.0 + gross) * (1.0 - cost_bps / 10000.0) - 1.0).dropna()


def bootstrap_excess(event_returns: np.ndarray, baseline_median: float, rng: np.random.Generator) -> dict:
    if len(event_returns) < 2:
        return {"ci_low": None, "ci_high": None, "p_one_sided": None}
    draws = rng.choice(event_returns, size=(BOOTSTRAPS, len(event_returns)), replace=True)
    excess = np.median(draws, axis=1) - baseline_median
    return {
        "ci_low": float(np.quantile(excess, 0.025)),
        "ci_high": float(np.quantile(excess, 0.975)),
        "p_one_sided": float((np.count_nonzero(excess <= 0) + 1) / (BOOTSTRAPS + 1)),
    }


def era(d: pd.Timestamp) -> str:
    if d.year <= 2015:
        return "2007-2015_development"
    if d.year <= 2020:
        return "2016-2020_validation"
    return "2021-2026_recent"


def summarize(trades: pd.DataFrame, price: pd.Series, hold_days: int, cost_bps: float, rng: np.random.Generator) -> dict:
    base = baseline_next_close(price, hold_days, cost_bps)
    if trades.empty:
        return {"n": 0}
    r = trades["net_return"].astype(float)
    baseline_median = float(base.median())
    out = {
        "n": int(len(trades)),
        "median_net_return": float(r.median()),
        "mean_net_return": float(r.mean()),
        "positive_rate": float((r > 0).mean()),
        "profit_factor": profit_factor(r),
        "median_mae": float(trades["mae"].median()),
        "median_mfe": float(trades["mfe"].median()),
        "max_trade_path_mae": float(trades["mae"].min()),
        "chained_trade_return": float((1.0 + r).prod() - 1.0),
        "trade_sequence_max_drawdown": max_drawdown_from_trades(r),
        "baseline_median": baseline_median,
        "median_excess_vs_all_days": float(r.median() - baseline_median),
        "bootstrap": bootstrap_excess(r.to_numpy(), baseline_median, rng),
        "eras": {},
    }
    for label in ["2007-2015_development", "2016-2020_validation", "2021-2026_recent"]:
        sub = trades[[era(d) == label for d in trades["entry_date"]]]
        sr = sub["net_return"] if len(sub) else pd.Series(dtype=float)
        out["eras"][label] = {
            "n": int(len(sub)),
            "median_net_return": float(sr.median()) if len(sub) else None,
            "positive_rate": float((sr > 0).mean()) if len(sub) else None,
            "profit_factor": profit_factor(sr) if len(sub) else None,
        }
    return out


def main() -> None:
    rng = np.random.default_rng(SEED)
    vix = fetch_fred("VIXCLS")
    vix3m = fetch_fred("VXVCLS")
    qqq = fetch_twelve_close("QQQ")
    signal = normalization_signal(vix, vix3m)
    signal_dates = candidate_signal_dates(signal, qqq.index)

    variants = []
    for hold in [7, 10, 15]:
        variants.append((f"hold_{hold}d_no_stop", hold, None, ROUNDTRIP_COST_BPS))
    for stop in [0.02, 0.03, 0.04]:
        variants.append((f"hold_10d_stop_{int(stop*100)}pct", 10, stop, ROUNDTRIP_COST_BPS))
    # Cost stress only for the frozen 10-day/no-stop implementation.
    for bps in [2.0, 10.0, 20.0]:
        variants.append((f"hold_10d_cost_{int(bps)}bps_roundtrip", 10, None, bps))

    results = {}
    trade_rows = {}
    for name, hold, stop, bps in variants:
        trades = simulate_trades(qqq, signal_dates, hold, roundtrip_cost_bps=bps, stop_pct=stop)
        results[name] = summarize(trades, qqq, hold, bps, rng)
        trade_rows[name] = [
            {
                "signal_date": str(d.date()),
                "entry_date": str(row["entry_date"].date()),
                "exit_date": str(row["exit_date"].date()),
                "net_return": float(row["net_return"]),
                "mae": float(row["mae"]),
                "mfe": float(row["mfe"]),
                "stop_hit": bool(row["stop_hit"]),
            }
            for d, row in trades.iterrows()
        ]

    core = results["hold_10d_no_stop"]
    stability_holds = [results[f"hold_{h}d_no_stop"] for h in [7, 10, 15]]
    recent = core.get("eras", {}).get("2021-2026_recent", {})
    validation = core.get("eras", {}).get("2016-2020_validation", {})
    ci_low = core.get("bootstrap", {}).get("ci_low")

    # Hard executable GO: positive all-era median edge, positive validation/recent medians,
    # bootstrap lower bound >0, enough total/recent events, and nearby holding periods positive.
    executable_go = bool(
        core.get("n", 0) >= 40
        and recent.get("n", 0) >= 10
        and core.get("median_excess_vs_all_days", -1) > 0
        and validation.get("median_net_return") is not None and validation["median_net_return"] > 0
        and recent.get("median_net_return") is not None and recent["median_net_return"] > 0
        and ci_low is not None and ci_low > 0
        and all(x.get("median_excess_vs_all_days", -1) > 0 for x in stability_holds)
    )

    payload = {
        "methodology": {
            "signal": "Frozen: VIX/VIX3M crosses from >1.00 to <=1.00 at close t",
            "entry": "QQQ close t+1; no same-close execution",
            "core_exit": "10 trading days after entry",
            "core_cost": "10 bps roundtrip (5 bps each side)",
            "signal_cooldown": f"{COOLDOWN_DAYS} trading days",
            "hold_stability": [7, 10, 15],
            "stop_tests": ["2% close stop", "3% close stop", "4% close stop"],
            "cost_stress_roundtrip_bps": [2, 10, 20],
            "bootstrap_resamples": BOOTSTRAPS,
            "purpose": "Executable validation of frozen QQQ VIX normalization candidate; no parameter optimization",
        },
        "signal_date_count_pre_execution": len(signal_dates),
        "results": results,
        "core_executable_go": executable_go,
        "trade_rows": trade_rows,
    }

    out = Path("artifacts/vix_execution")
    out.mkdir(parents=True, exist_ok=True)
    (out / "vix_normalization_execution.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
