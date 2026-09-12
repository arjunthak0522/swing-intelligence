from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from reentry_cash_policy_validation import historical_proxy_states, forward_return
from reentry_confidence import feature_frame
from reentry_walkforward_validation import generate_decisions
from reentry_secondary_confirmation import nyse_symbols, ticker_close

START = "2017-01-01"
HORIZONS = (5, 10, 15, 30, 60, 90)
BATCH = 140
ROUND_TRIP_COST = 0.001
OUTDIR = Path("artifacts/reentry_t2108_incremental")


def summarize(x: pd.Series) -> dict:
    x = pd.to_numeric(x, errors="coerce").dropna()
    if x.empty:
        return {"n": 0, "median": None, "mean": None, "positive_rate": None}
    return {
        "n": int(len(x)),
        "median": float(x.median()),
        "mean": float(x.mean()),
        "positive_rate": float((x > 0).mean()),
    }


def build_t2108_history(index: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict]:
    symbols = nyse_symbols()
    above = pd.Series(0.0, index=index)
    valid = pd.Series(0.0, index=index)

    for start in range(0, len(symbols), BATCH):
        batch = symbols[start:start + BATCH]
        frame = yf.download(
            batch,
            start=START,
            end=(index.max() + pd.Timedelta(days=7)).strftime("%Y-%m-%d"),
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
            timeout=30,
        )
        for ticker in batch:
            closes = ticker_close(frame, ticker)
            if closes.empty:
                continue
            closes.index = pd.to_datetime(closes.index).tz_localize(None).normalize()
            closes = closes[~closes.index.duplicated(keep="last")].sort_index()
            ma40 = closes.rolling(40, min_periods=40).mean()
            joined = pd.concat([closes.rename("close"), ma40.rename("ma40")], axis=1).reindex(index)
            ok = joined["close"].notna() & joined["ma40"].notna()
            if not ok.any():
                continue
            valid.loc[ok] += 1.0
            above.loc[ok & (joined["close"] > joined["ma40"])] += 1.0

    value = 100.0 * above / valid.replace(0, np.nan)
    out = pd.DataFrame(index=index)
    out["T2108"] = value
    out["T2108_delta1"] = value.diff()
    out["T2108_delta3"] = value.diff(3)
    out["valid_count"] = valid
    out["coverage_vs_current_universe"] = valid / max(1, len(symbols))
    out["low_40"] = value < 40
    out["oversold_20"] = value < 20
    out["rising_1pt"] = out["T2108_delta1"] >= 1.0
    out["low_and_rising"] = out["low_40"] & out["rising_1pt"]
    out["cross_above_40"] = (value >= 40) & (value.shift(1) < 40)
    meta = {
        "current_nyse_universe_size": len(symbols),
        "historical_reconstruction_caveat": "Current-listed NYSE constituents are projected backward. This creates survivorship and listing-history bias; results are exploratory and cannot by themselves promote T2108 into REENTRY_UNIFIED_v1 decision logic.",
        "start": str(index.min().date()),
        "end": str(index.max().date()),
        "median_valid_count": int(valid.median()),
        "min_valid_count": int(valid[valid > 0].min()) if (valid > 0).any() else 0,
    }
    return out, meta


def episode_starts(signal: pd.Series) -> pd.Series:
    s = signal.fillna(False).astype(bool)
    return s & ~s.shift(1, fill_value=False)


def forward_tables(states: pd.DataFrame, frame: pd.DataFrame, t: pd.DataFrame) -> dict:
    starts = episode_starts(states["deployment_signal"].eq("DEPLOY"))
    masks = {
        "ALL_DEPLOY_EPISODES": starts,
        "T2108_BELOW_40": starts & t["low_40"].fillna(False),
        "T2108_BELOW_40_AND_RISING": starts & t["low_and_rising"].fillna(False),
        "T2108_BELOW_20": starts & t["oversold_20"].fillna(False),
        "T2108_CROSS_ABOVE_40": starts & t["cross_above_40"].fillna(False),
    }
    out = {}
    for label, mask in masks.items():
        block = {"episodes": int(mask.sum()), "SPY": {}, "QQQ": {}}
        for sym in ("SPY", "QQQ"):
            px = frame[sym].reindex(states.index)
            for h in HORIZONS:
                block[sym][str(h)] = summarize(forward_return(px, h).loc[mask])
        out[label] = block
    return out


def incremental_vs_all(results: dict) -> dict:
    base = results["ALL_DEPLOY_EPISODES"]
    out = {}
    for label, block in results.items():
        if label == "ALL_DEPLOY_EPISODES":
            continue
        out[label] = {"SPY": {}, "QQQ": {}}
        for sym in ("SPY", "QQQ"):
            for h in HORIZONS:
                a = block[sym][str(h)]
                b = base[sym][str(h)]
                out[label][sym][str(h)] = {
                    "n": a["n"],
                    "median_return_delta": None if a["median"] is None or b["median"] is None else float(a["median"] - b["median"]),
                    "positive_rate_delta": None if a["positive_rate"] is None or b["positive_rate"] is None else float(a["positive_rate"] - b["positive_rate"]),
                }
    return out


def waiting_cost(states: pd.DataFrame, frame: pd.DataFrame, t: pd.DataFrame, max_wait: int = 5) -> dict:
    starts = np.flatnonzero(episode_starts(states["deployment_signal"].eq("DEPLOY")).to_numpy())
    rows = []
    for pos in starts:
        if bool(t["low_and_rising"].iloc[pos]) if pd.notna(t["low_and_rising"].iloc[pos]) else False:
            wait = 0
        else:
            wait = None
            for k in range(1, max_wait + 1):
                j = pos + k
                if j >= len(t):
                    break
                if bool(t["low_and_rising"].iloc[j]) if pd.notna(t["low_and_rising"].iloc[j]) else False:
                    wait = k
                    break
        rec = {"signal_pos": int(pos), "wait_sessions": wait}
        if wait is not None and pos + 1 + wait < len(states):
            for sym in ("SPY", "QQQ"):
                px = frame[sym].reindex(states.index)
                immediate = float(px.iloc[pos + 1])
                delayed = float(px.iloc[pos + 1 + wait])
                rec[f"{sym}_entry_cost_of_waiting"] = delayed / immediate - 1.0
        rows.append(rec)
    r = pd.DataFrame(rows)
    confirmed = r[r["wait_sessions"].notna()].copy() if not r.empty else r
    return {
        "deploy_episode_count": int(len(rows)),
        "confirmed_within_5_sessions": int(len(confirmed)),
        "confirmation_rate": float(len(confirmed) / len(rows)) if rows else None,
        "median_wait_sessions": float(confirmed["wait_sessions"].median()) if len(confirmed) else None,
        "share_immediate": float((confirmed["wait_sessions"] == 0).mean()) if len(confirmed) else None,
        "SPY_entry_cost_of_waiting": summarize(confirmed.get("SPY_entry_cost_of_waiting", pd.Series(dtype=float))),
        "QQQ_entry_cost_of_waiting": summarize(confirmed.get("QQQ_entry_cost_of_waiting", pd.Series(dtype=float))),
        "interpretation": "Positive entry_cost_of_waiting means requiring T2108 confirmation bought later at a higher price than the original RE-ENTRY episode entry.",
    }


def redundancy(states: pd.DataFrame, t: pd.DataFrame) -> dict:
    common = states.index.intersection(t.index)
    x = t.loc[common, "T2108"]
    b50 = pd.to_numeric(states.loc[common, "B50"], errors="coerce") * 100.0
    good = x.notna() & b50.notna()
    deploy = states.loc[common, "deployment_signal"].eq("DEPLOY")
    return {
        "pearson_corr_with_existing_B50_proxy": float(x[good].corr(b50[good])) if good.sum() > 3 else None,
        "n_common": int(good.sum()),
        "share_deploy_episodes_below_40": float((t.loc[common, "low_40"] & deploy).sum() / max(1, deploy.sum())),
        "share_proxy_oversold_days_below_40": float((t.loc[common, "low_40"] & states.loc[common, "oversold_proxy"]).sum() / max(1, states.loc[common, "oversold_proxy"].sum())),
    }


def verdict(results: dict, inc: dict, wait: dict, red: dict) -> dict:
    key = inc["T2108_BELOW_40_AND_RISING"]
    n = results["T2108_BELOW_40_AND_RISING"]["episodes"]
    checks = {}
    for sym in ("SPY", "QQQ"):
        for h in (10, 30):
            cell = key[sym][str(h)]
            checks[f"{sym}_{h}D_nonnegative_increment"] = bool(cell["n"] >= 25 and cell["median_return_delta"] is not None and cell["median_return_delta"] >= 0)
            checks[f"{sym}_{h}D_no_large_hit_rate_damage"] = bool(cell["n"] >= 25 and cell["positive_rate_delta"] is not None and cell["positive_rate_delta"] >= -0.03)
    timing_ok = bool(
        wait.get("median_wait_sessions") is not None
        and wait["median_wait_sessions"] <= 1.0
        and (wait["SPY_entry_cost_of_waiting"].get("median") or 0) <= 0.0025
        and (wait["QQQ_entry_cost_of_waiting"].get("median") or 0) <= 0.0025
    )
    incremental_ok = n >= 25 and all(checks.values())
    highly_redundant = (red.get("pearson_corr_with_existing_B50_proxy") or 0) >= 0.85
    if incremental_ok and timing_ok and not highly_redundant:
        v = "PROMOTE_TO_SECONDARY_CONFIRMATION_CANDIDATE"
    elif incremental_ok:
        v = "KEEP_CONTEXT_ONLY_TIMING_OR_REDUNDANCY_LIMIT"
    else:
        v = "KEEP_CONTEXT_ONLY_NO_INCREMENTAL_EDGE"
    return {
        "verdict": v,
        "decision_logic_change_authorized": False,
        "incremental_checks": checks,
        "incremental_quality_pass": incremental_ok,
        "timing_cost_pass": timing_ok,
        "high_redundancy_flag": highly_redundant,
        "hard_limit": "Current-universe historical reconstruction has survivorship bias. Even a positive result cannot directly promote T2108 into the DEPLOY trigger without point-in-time breadth history or sufficient prospective history.",
    }


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    frame, metadata = feature_frame(return_metadata=True, require_same_day=False)
    decisions = generate_decisions(frame)
    states = historical_proxy_states(frame, decisions)
    aligned = frame.reindex(states.index)
    t2108, tmeta = build_t2108_history(pd.DatetimeIndex(states.index).tz_localize(None).normalize())
    t2108.index = states.index
    results = forward_tables(states, aligned, t2108)
    inc = incremental_vs_all(results)
    wait = waiting_cost(states, aligned, t2108)
    red = redundancy(states, t2108)
    decision = verdict(results, inc, wait, red)

    payload = {
        "status": "COMPLETE",
        "question": "Does a T2108-equivalent add useful incremental confirmation to existing RE-ENTRY DEPLOY episodes, or mainly delay an already validated early-entry signal?",
        "date_range": [str(states.index.min().date()), str(states.index.max().date())],
        "methodology": {
            "entry": "signal known at close t; hypothetical entry close t+1",
            "horizons": list(HORIZONS),
            "round_trip_cost": ROUND_TRIP_COST,
            "episode_sampling": "first session of each contiguous historical proxy DEPLOY episode",
            "t2108_candidate": "current-listed NYSE non-ETF equities above 40-day adjusted-close SMA",
            "confirmation_rule_tested": "T2108 < 40 and rises at least 1 percentage point day over day",
            "no_change_to_live_engine": True,
        },
        "data_metadata": metadata,
        "t2108_metadata": tmeta,
        "forward_results": results,
        "incremental_vs_all_deploy": inc,
        "waiting_cost": wait,
        "redundancy": red,
        "promotion_gate": decision,
    }
    (OUTDIR / "t2108_incremental_validation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    t2108.to_csv(OUTDIR / "t2108_reconstructed_history.csv", index_label="date")
    print(json.dumps(payload["promotion_gate"], indent=2))
    print(json.dumps({"waiting_cost": wait, "redundancy": red}, indent=2))


if __name__ == "__main__":
    main()
